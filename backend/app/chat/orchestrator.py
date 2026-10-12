"""One chat turn end-to-end: run the agent, verify its citations, stream, persist.

The answer is streamed only after it passes the grounding checks, so an analyst
never reads text that later turns out to be unsupported. While the agent works,
transient `data-status` parts show what it is searching.
"""

import asyncio
from collections.abc import AsyncIterator
from typing import Any
from uuid import UUID, uuid4

import openai
import structlog
from pydantic_ai.exceptions import (
    ModelAPIError,
    UnexpectedModelBehavior,
    UsageLimitExceeded,
)
from sqlalchemy.exc import SQLAlchemyError
from supabase import AsyncClient

from app.assistant.agent import USAGE_LIMITS, DocumentAgent
from app.assistant.deps import DocumentAgentDeps
from app.assistant.outputs import Citation, GroundedAnswer
from app.chat.history import to_model_history
from app.chat.messages import UIMessage, text_from_parts, title_from_text
from app.chat.streaming import DONE, data_part, error_event, sse, text_deltas
from app.database import chats
from app.grounding.validator import validate_grounding
from app.retrieval.retriever import DocumentRetriever
from app.retrieval.types import RetrievedPassage

log = structlog.get_logger()

GROUNDING_FAILED = (
    "I couldn't produce an answer whose citations check out against the filings. "
    "Try narrowing the question to a company, metric, or fiscal year."
)
TOO_MANY_STEPS = (
    "This question needed more searching than one answer allows. "
    "Try splitting it into smaller questions, e.g. one company at a time."
)
UPSTREAM_FAILED = "The answer service is unavailable right now. Please try again in a moment."
RETRIEVAL_FAILED = "Searching the filings failed. Please try again in a moment."


async def stream_grounded_turn(
    service: AsyncClient,
    agent: DocumentAgent,
    retriever: DocumentRetriever,
    user_id: UUID,
    thread: dict[str, Any],
    user_message: UIMessage,
) -> AsyncIterator[str]:
    question = text_from_parts(user_message.parts)
    thread_id = UUID(thread["id"])
    history = to_model_history(await chats.list_messages(service, thread_id))
    statuses: asyncio.Queue[str] = asyncio.Queue()
    deps = DocumentAgentDeps(
        user_id=user_id, thread_id=thread_id, retriever=retriever, on_status=statuses.put_nowait
    )
    message_id = str(uuid4())
    logger = log.bind(thread_id=str(thread_id), message_id=message_id)

    yield sse({"type": "start", "messageId": message_id})
    run = asyncio.create_task(
        agent.run(question, deps=deps, message_history=history, usage_limits=USAGE_LIMITS)
    )
    try:
        async for status in relay_statuses(run, statuses):
            yield sse(data_part("status", {"message": status}, id="status", transient=True))
        result = run.result()
    except UnexpectedModelBehavior as exc:
        # Includes running out of output retries on grounding violations.
        logger.warning("agent_failed_grounding", error=str(exc))
        yield error_event(GROUNDING_FAILED)
        yield DONE
        return
    except UsageLimitExceeded as exc:
        logger.warning("agent_usage_limit", error=str(exc))
        yield error_event(TOO_MANY_STEPS)
        yield DONE
        return
    except (ModelAPIError, openai.APIError) as exc:
        logger.error("upstream_llm_failed", error=str(exc))
        yield error_event(UPSTREAM_FAILED)
        yield DONE
        return
    except SQLAlchemyError as exc:
        logger.error("retrieval_failed", error=str(exc))
        yield error_event(RETRIEVAL_FAILED)
        yield DONE
        return
    finally:
        # A disconnected client cancels this generator; don't keep paying for the run.
        run.cancel()

    answer = result.output
    # The output validator already enforced this; checked again so nothing
    # ungrounded is ever streamed or stored, whatever happens upstream.
    errors = validate_grounding(answer, deps.retrieved)
    if errors:
        logger.error("ungrounded_answer_reached_orchestrator", errors=errors)
        yield error_event(GROUNDING_FAILED)
        yield DONE
        return

    text_id = str(uuid4())
    yield sse({"type": "text-start", "id": text_id})
    for delta in text_deltas(answer.answer):
        yield sse({"type": "text-delta", "id": text_id, "delta": delta})
    yield sse({"type": "text-end", "id": text_id})

    data_parts = answer_data_parts(answer, deps.retrieved)
    for part in data_parts:
        yield sse(part)

    title = title_from_text(question) if thread["title"] == chats.DEFAULT_THREAD_TITLE else None
    usage = result.usage
    await chats.save_turn(
        service,
        thread_id,
        [
            {"role": "user", "content": question, "parts": user_message.parts},
            {
                "id": message_id,
                "role": "assistant",
                "content": answer.answer,
                "parts": [{"type": "text", "text": answer.answer}, *data_parts],
                "usage": {
                    "requests": usage.requests,
                    "tool_calls": usage.tool_calls,
                    "input_tokens": usage.input_tokens,
                    "output_tokens": usage.output_tokens,
                },
            },
        ],
        title,
    )
    await chats.save_citations(
        service,
        message_id,
        [
            {"chunk_id": str(c.chunk_id), "citation_index": c.index, "quote": c.quote}
            for c in answer.citations
        ],
    )

    yield sse({"type": "finish"})
    yield DONE


async def relay_statuses(run: asyncio.Task, statuses: asyncio.Queue[str]) -> AsyncIterator[str]:
    """Yield status messages as they arrive until the agent run finishes."""
    while True:
        getter = asyncio.create_task(statuses.get())
        try:
            await asyncio.wait({run, getter}, return_when=asyncio.FIRST_COMPLETED)
        finally:
            if not getter.done():
                getter.cancel()
        if getter.done() and not getter.cancelled():
            yield getter.result()
        elif run.done():
            return


def answer_data_parts(
    answer: GroundedAnswer, retrieved: dict[UUID, RetrievedPassage]
) -> list[dict[str, Any]]:
    """Parts the frontend renders next to the text: the answer status and one per citation."""
    citations = sorted(answer.citations, key=lambda c: c.index)
    return [
        data_part("grounding", {"status": answer.status}, id="grounding"),
        *(
            data_part("citation", citation_data(c, retrieved[c.chunk_id]), id=f"citation-{c.index}")
            for c in citations
        ),
    ]


def citation_data(citation: Citation, passage: RetrievedPassage) -> dict[str, Any]:
    return {
        "index": citation.index,
        "chunkId": str(citation.chunk_id),
        "quote": citation.quote,
        "ticker": passage.ticker,
        "companyName": passage.company_name,
        "filingType": passage.filing_type,
        "filingDate": passage.filing_date.isoformat(),
        "fiscalYear": passage.fiscal_year,
        "page": passage.page,
        "pageEnd": passage.page_end,
        "section": passage.section,
        "sourceUrl": passage.source_url,
        "excerpt": passage.content,
    }
