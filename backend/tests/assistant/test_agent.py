"""The agent with a scripted model: tools, retries on grounding violations, failing closed."""

import asyncio
from uuid import uuid4

import pytest
from pydantic_ai.exceptions import UnexpectedModelBehavior
from pydantic_ai.messages import ModelResponse, RetryPromptPart, ToolCallPart
from pydantic_ai.models.function import AgentInfo, FunctionModel

from app.assistant.agent import SEARCH_TOP_K, build_agent, search_status
from app.assistant.deps import DocumentAgentDeps
from app.retrieval.types import SearchFilters

QUOTE = "iPhone net sales were relatively flat during 2024"


class FakeRetriever:
    def __init__(self, passages):
        self.passages = passages
        self.searches: list[tuple[str, SearchFilters, int]] = []
        self.windows: list[tuple] = []

    async def search(self, query, filters=None, *, top_k=None, neighbor_radius=None):
        self.searches.append((query, filters, top_k))
        return self.passages

    async def read_chunk(self, chunk_id):
        return next((p for p in self.passages if p.chunk_id == chunk_id), None)

    async def read_surrounding_chunks(self, chunk_id, radius=None):
        self.windows.append((chunk_id, radius))
        return [p for p in self.passages if p.chunk_id == chunk_id]


def final(info: AgentInfo, *, chunk_id, quote=QUOTE, text="iPhone sales were flat [1].", status="answered"):
    args = {
        "status": status,
        "answer": text,
        "citations": [{"index": 1, "chunk_id": str(chunk_id), "quote": quote}] if chunk_id else [],
    }
    return ModelResponse(parts=[ToolCallPart(info.output_tools[0].name, args)])


def search_call(**args):
    return ModelResponse(parts=[ToolCallPart("search_filings", {"query": "iPhone net sales", **args})])


def retry_feedback(messages) -> list[str]:
    return [
        part.model_response()
        for message in messages
        for part in getattr(message, "parts", [])
        if isinstance(part, RetryPromptPart)
    ]


def run_agent(script, passages):
    """`script(call_number, messages, info)` plays the model."""
    calls = []

    def model(messages, info):
        calls.append(messages)
        return script(len(calls), messages, info)

    retriever = FakeRetriever(passages)
    statuses: list[str] = []
    deps = DocumentAgentDeps(
        user_id=uuid4(), thread_id=uuid4(), retriever=retriever, on_status=statuses.append
    )
    result = asyncio.run(build_agent(FunctionModel(model)).run("How did iPhone sales change?", deps=deps))
    return result, deps, retriever, statuses, calls


def test_search_then_grounded_answer(make_passage):
    passage = make_passage()

    def script(n, messages, info):
        return search_call(tickers=["AAPL"], fiscal_years=[2024]) if n == 1 else final(info, chunk_id=passage.chunk_id)

    result, deps, retriever, statuses, _ = run_agent(script, [passage])

    assert result.output.status == "answered"
    assert result.output.citations[0].chunk_id == passage.chunk_id
    assert passage.chunk_id in deps.retrieved
    assert retriever.searches == [
        ("iPhone net sales", SearchFilters(tickers=["AAPL"], fiscal_years=[2024]), SEARCH_TOP_K)
    ]
    assert statuses == ["Searching AAPL FY2024: iPhone net sales"]


def test_search_results_show_the_model_citable_chunk_ids(make_passage):
    passage = make_passage()
    seen = []

    def script(n, messages, info):
        if n == 1:
            return search_call()
        seen.append(str(messages[-1].parts[0].content))
        return final(info, chunk_id=passage.chunk_id)

    run_agent(script, [passage])

    assert f"[chunk:{passage.chunk_id}]" in seen[0]


def test_neighbors_shown_to_the_model_are_citable(make_passage):
    neighbor = make_passage(1)
    hit = make_passage(0, neighbors=[neighbor])

    def script(n, messages, info):
        return search_call() if n == 1 else final(info, chunk_id=neighbor.chunk_id)

    result, deps, *_ = run_agent(script, [hit])

    assert result.output.citations[0].chunk_id == neighbor.chunk_id
    assert deps.retrieved[neighbor.chunk_id].neighbors == []


def test_unretrieved_citation_is_sent_back_and_fixed(make_passage):
    passage = make_passage()

    def script(n, messages, info):
        if n == 1:
            return search_call()
        if n == 2:
            return final(info, chunk_id=uuid4())  # a chunk the model never saw
        return final(info, chunk_id=passage.chunk_id)

    result, _, _, _, calls = run_agent(script, [passage])

    assert result.output.citations[0].chunk_id == passage.chunk_id
    [feedback] = retry_feedback(calls[2])
    assert "not returned by a tool" in feedback


def test_misquote_is_sent_back_with_the_reason(make_passage):
    passage = make_passage()

    def script(n, messages, info):
        if n == 1:
            return search_call()
        if n == 2:
            return final(info, chunk_id=passage.chunk_id, quote="iPhone net sales grew strongly in 2024")
        return final(info, chunk_id=passage.chunk_id)

    _, _, _, _, calls = run_agent(script, [passage])

    assert "does not appear" in retry_feedback(calls[2])[0]


def test_persistently_ungrounded_answer_fails_closed(make_passage):
    passage = make_passage()

    def script(n, messages, info):
        return search_call() if n == 1 else final(info, chunk_id=passage.chunk_id, quote="made up text here")

    with pytest.raises(UnexpectedModelBehavior):
        run_agent(script, [passage])


def test_answer_without_searching_cannot_cite_anything(make_passage):
    passage = make_passage()

    def script(n, messages, info):
        return final(info, chunk_id=passage.chunk_id)  # knows an id but never retrieved it

    with pytest.raises(UnexpectedModelBehavior):
        run_agent(script, [passage])


def test_insufficient_evidence_without_citations_is_accepted(make_passage):
    def script(n, messages, info):
        if n == 1:
            return search_call()
        return final(
            info,
            chunk_id=None,
            text="The filings do not say whether generative AI improved margins.",
            status="insufficient_evidence",
        )

    result, *_ = run_agent(script, [make_passage()])

    assert result.output.status == "insufficient_evidence"
    assert result.output.citations == []


def test_read_surrounding_chunks_clamps_radius(make_passage):
    passage = make_passage()

    def script(n, messages, info):
        if n == 1:
            return ModelResponse(
                parts=[
                    ToolCallPart(
                        "read_surrounding_chunks", {"chunk_id": str(passage.chunk_id), "radius": 50}
                    )
                ]
            )
        return final(info, chunk_id=passage.chunk_id)

    _, deps, retriever, *_ = run_agent(script, [passage])

    assert retriever.windows == [(passage.chunk_id, 2)]
    assert passage.chunk_id in deps.retrieved


def test_search_status_describes_scope():
    assert search_status("capex", SearchFilters()) == "Searching all filings: capex"
    assert (
        search_status("capex", SearchFilters(tickers=["MSFT", "AMZN"], fiscal_years=[2025]))
        == "Searching MSFT, AMZN FY2025: capex"
    )
