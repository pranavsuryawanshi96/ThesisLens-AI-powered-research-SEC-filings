"""A full turn with a scripted model: what is streamed, what is stored, and what is not."""

import asyncio
import json
from uuid import UUID, uuid4

import pytest
from pydantic_ai.messages import (
    ModelRequest,
    ModelResponse,
    ToolCallPart,
    ToolReturnPart,
    UserPromptPart,
)
from pydantic_ai.models.function import FunctionModel
from sqlalchemy.exc import OperationalError

from app.assistant.agent import build_agent
from app.chat import orchestrator
from app.chat.messages import UIMessage
from app.database import chats

QUESTION = "How did iPhone sales change in 2024?"
QUOTE = "iPhone net sales were relatively flat during 2024"


class FakeRetriever:
    def __init__(self, passages, error: Exception | None = None):
        self.passages = passages
        self.error = error

    async def search(self, query, filters=None, *, top_k=None, neighbor_radius=None):
        if self.error:
            raise self.error
        return self.passages


@pytest.fixture
def store(monkeypatch):
    """Stand-ins for chats persistence; `history` is what list_messages returns."""
    store = {"history": [], "turns": [], "citations": []}

    async def list_messages(_client, thread_id):
        return store["history"]

    async def save_turn(_client, thread_id, messages, title):
        store["turns"].append({"thread_id": thread_id, "messages": messages, "title": title})

    async def save_citations(_client, message_id, citations):
        store["citations"].append((message_id, citations))

    monkeypatch.setattr(chats, "list_messages", list_messages)
    monkeypatch.setattr(chats, "save_turn", save_turn)
    monkeypatch.setattr(chats, "save_citations", save_citations)
    return store


def scripted_model(chunk_id: UUID | None, *, quote: str = QUOTE, seen: list | None = None):
    """Searches once, then answers citing `chunk_id`."""

    def model(messages, info):
        if seen is not None:
            seen.append(messages)
        searched = any(isinstance(part, ToolReturnPart) for m in messages for part in m.parts)
        if not searched:
            return ModelResponse(parts=[ToolCallPart("search_filings", {"query": "iPhone net sales"})])
        args = {
            "status": "answered",
            "answer": "iPhone net sales were flat in 2024 [1].",
            "citations": [{"index": 1, "chunk_id": str(chunk_id), "quote": quote}],
        }
        return ModelResponse(parts=[ToolCallPart(info.output_tools[0].name, args)])

    return FunctionModel(model)


def run_turn(model, retriever, title: str = chats.DEFAULT_THREAD_TITLE) -> list:
    thread = {"id": str(uuid4()), "title": title}
    message = UIMessage(id="u1", role="user", parts=[{"type": "text", "text": QUESTION}])

    async def collect():
        stream = orchestrator.stream_grounded_turn(
            "service", build_agent(model), retriever, uuid4(), thread, message
        )
        return [frame async for frame in stream]

    frames = asyncio.run(collect())
    return [
        "[DONE]" if frame == "data: [DONE]\n\n" else json.loads(frame.removeprefix("data: "))
        for frame in frames
    ]


def types(events) -> list[str]:
    return [e if e == "[DONE]" else e["type"] for e in events]


def test_grounded_turn_streams_status_text_and_citations_then_persists(store, make_passage):
    passage = make_passage()

    events = run_turn(scripted_model(passage.chunk_id), FakeRetriever([passage]))

    assert types(events) == [
        "start",
        "data-status",
        "text-start",
        *["text-delta"] * len([e for e in events if e != "[DONE]" and e["type"] == "text-delta"]),
        "text-end",
        "data-grounding",
        "data-citation",
        "finish",
        "[DONE]",
    ]
    status = events[1]
    assert status["transient"] is True
    assert status["data"]["message"] == "Searching all filings: iPhone net sales"
    reply = "".join(e["delta"] for e in events if e != "[DONE]" and e["type"] == "text-delta")
    assert reply == "iPhone net sales were flat in 2024 [1]."

    citation = next(e for e in events if e != "[DONE]" and e["type"] == "data-citation")
    assert citation["id"] == "citation-1"
    assert citation["data"] | {
        "chunkId": str(passage.chunk_id),
        "quote": QUOTE,
        "ticker": "AAPL",
        "filingType": "10-K",
        "filingDate": "2024-11-01",
        "fiscalYear": 2024,
        "page": 24,
        "excerpt": passage.content,
    } == citation["data"]

    [turn] = store["turns"]
    assert turn["title"] == QUESTION
    user_msg, assistant_msg = turn["messages"]
    assert user_msg["content"] == QUESTION
    assert assistant_msg["id"] == events[0]["messageId"]
    assert assistant_msg["content"] == reply
    # Transient status parts are live-only; citations are stored with the message.
    assert [p["type"] for p in assistant_msg["parts"]] == ["text", "data-grounding", "data-citation"]
    assert assistant_msg["usage"]["requests"] == 2
    assert store["citations"] == [
        (
            events[0]["messageId"],
            [{"chunk_id": str(passage.chunk_id), "citation_index": 1, "quote": QUOTE}],
        )
    ]


def test_ungrounded_answer_is_never_streamed_or_saved(store, make_passage):
    passage = make_passage()

    events = run_turn(scripted_model(passage.chunk_id, quote="made-up quote text"), FakeRetriever([passage]))

    assert "text-delta" not in types(events)
    assert types(events)[-2:] == ["error", "[DONE]"]
    assert events[-2]["errorText"] == orchestrator.GROUNDING_FAILED
    assert store["turns"] == [] and store["citations"] == []


def test_retrieval_failure_sends_error_and_saves_nothing(store, make_passage):
    failing = FakeRetriever([], error=OperationalError("select", {}, Exception("connection lost")))

    events = run_turn(scripted_model(uuid4()), failing)

    assert events[-2]["errorText"] == orchestrator.RETRIEVAL_FAILED
    assert store["turns"] == []


def test_runaway_searching_hits_the_usage_limit(store, make_passage):
    def always_search(messages, info):
        return ModelResponse(parts=[ToolCallPart("search_filings", {"query": "more"})])

    events = run_turn(FunctionModel(always_search), FakeRetriever([make_passage()]))

    assert events[-2]["errorText"] == orchestrator.TOO_MANY_STEPS
    assert store["turns"] == []


def test_previous_messages_are_replayed_to_the_model(store, make_passage):
    passage = make_passage()
    store["history"] = [
        {"id": "1", "role": "user", "parts": [{"type": "text", "text": "Tell me about Apple."}]},
        {"id": "2", "role": "assistant", "parts": [{"type": "text", "text": "Apple sells iPhones [1]."}]},
    ]
    seen: list = []

    run_turn(scripted_model(passage.chunk_id, seen=seen), FakeRetriever([passage]))

    first_call = seen[0]
    prompts = [
        part.content
        for message in first_call
        if isinstance(message, ModelRequest)
        for part in message.parts
        if isinstance(part, UserPromptPart)
    ]
    assert prompts == ["Tell me about Apple.", QUESTION]


def test_custom_thread_title_is_kept(store, make_passage):
    passage = make_passage()

    run_turn(scripted_model(passage.chunk_id), FakeRetriever([passage]), title="Apple deep dive")

    assert store["turns"][0]["title"] is None
