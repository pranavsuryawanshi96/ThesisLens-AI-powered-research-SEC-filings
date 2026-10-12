"""The PydanticAI agent: bounded retrieval tools in, a grounded answer out.

The output validator runs the grounding contract on every answer the model
proposes; violations go back to the model as ModelRetry feedback, and an answer
that still fails after OUTPUT_RETRIES makes the run fail rather than return.
"""

from pathlib import Path
from uuid import UUID

from openai import AsyncOpenAI
from pydantic_ai import Agent, ModelRetry, RunContext
from pydantic_ai.models import Model
from pydantic_ai.models.openai import OpenAIChatModel
from pydantic_ai.providers.openai import OpenAIProvider
from pydantic_ai.usage import UsageLimits

from app.assistant.deps import DocumentAgentDeps
from app.assistant.outputs import GroundedAnswer
from app.config import settings
from app.grounding.validator import validate_grounding
from app.retrieval.retriever import format_chunk, format_passages_for_agent
from app.retrieval.types import SearchFilters

INSTRUCTIONS = Path(__file__).with_name("instructions.md").read_text(encoding="utf-8")

# Six hits with one neighbor each is ~9k tokens per search; a five-year comparison
# runs five searches, so larger pages would crowd out the conversation.
SEARCH_TOP_K = 6
MAX_SURROUNDING_RADIUS = 2
OUTPUT_RETRIES = 2
# Caps one turn's cost if the model loops on searches.
USAGE_LIMITS = UsageLimits(request_limit=12, tool_calls_limit=15)

DocumentAgent = Agent[DocumentAgentDeps, GroundedAnswer]


def create_chat_model(openai: AsyncOpenAI) -> Model:
    return OpenAIChatModel(settings.openai_chat_model, provider=OpenAIProvider(openai_client=openai))


def build_agent(model: Model) -> DocumentAgent:
    agent = Agent(
        model,
        deps_type=DocumentAgentDeps,
        output_type=GroundedAnswer,
        instructions=INSTRUCTIONS,
        retries={"output": OUTPUT_RETRIES, "tools": 2},
        tools=[search_filings, read_chunk, read_surrounding_chunks],
    )
    agent.output_validator(check_grounding)
    return agent


async def search_filings(
    ctx: RunContext[DocumentAgentDeps],
    query: str,
    tickers: list[str] | None = None,
    fiscal_years: list[int] | None = None,
) -> str:
    """Search the SEC filings corpus and return the most relevant passages.

    Args:
        query: What to look for, in the filing's own vocabulary.
        tickers: Limit to these companies, e.g. ["AAPL"]. Omit to search all.
        fiscal_years: Limit to these fiscal years, e.g. [2024, 2025]. Omit to search all.
    """
    filters = SearchFilters(tickers=tickers, fiscal_years=fiscal_years)
    ctx.deps.on_status(search_status(query, filters))
    passages = await ctx.deps.retriever.search(query, filters, top_k=SEARCH_TOP_K)
    ctx.deps.remember(passages)
    return format_passages_for_agent(passages)


async def read_chunk(ctx: RunContext[DocumentAgentDeps], chunk_id: UUID) -> str:
    """Read one passage in full by its chunk id."""
    passage = await ctx.deps.retriever.read_chunk(chunk_id)
    if passage is None:
        return f"No chunk with id {chunk_id}."
    ctx.deps.remember([passage])
    return format_chunk(passage)


async def read_surrounding_chunks(
    ctx: RunContext[DocumentAgentDeps], chunk_id: UUID, radius: int = 1
) -> str:
    """Read a passage together with the passages just before and after it in the same filing.

    Args:
        chunk_id: The passage to center on.
        radius: How many passages to include on each side (1 or 2).
    """
    radius = max(1, min(radius, MAX_SURROUNDING_RADIUS))
    window = await ctx.deps.retriever.read_surrounding_chunks(chunk_id, radius)
    if not window:
        return f"No chunk with id {chunk_id}."
    ctx.deps.remember(window)
    return "\n\n".join(format_chunk(p, is_match=p.chunk_id == chunk_id) for p in window)


async def check_grounding(ctx: RunContext[DocumentAgentDeps], answer: GroundedAnswer) -> GroundedAnswer:
    errors = validate_grounding(answer, ctx.deps.retrieved)
    if errors:
        raise ModelRetry("The answer failed citation checks:\n- " + "\n- ".join(errors))
    return answer


def search_status(query: str, filters: SearchFilters) -> str:
    scope = " ".join(
        part
        for part in (
            ", ".join(filters.tickers or []),
            ", ".join(f"FY{year}" for year in filters.fiscal_years or []),
        )
        if part
    )
    return f"Searching {scope or 'all filings'}: {query}"
