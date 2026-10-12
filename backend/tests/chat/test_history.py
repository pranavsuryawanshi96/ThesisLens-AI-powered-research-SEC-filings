from pydantic_ai.messages import ModelRequest, ModelResponse, TextPart, UserPromptPart

from app.chat.history import MAX_HISTORY_MESSAGES, to_model_history


def row(role: str, *parts: dict) -> dict:
    return {"id": "m", "role": role, "parts": list(parts)}


def text(value: str) -> dict:
    return {"type": "text", "text": value}


def test_user_and_assistant_text_become_request_and_response():
    history = to_model_history([row("user", text("Apple revenue?")), row("assistant", text("It grew [1]."))])

    assert len(history) == 2
    assert isinstance(history[0], ModelRequest)
    assert history[0].parts == [UserPromptPart(content="Apple revenue?", timestamp=history[0].parts[0].timestamp)]
    assert isinstance(history[1], ModelResponse)
    assert history[1].parts == [TextPart(content="It grew [1].")]


def test_citation_and_status_parts_are_not_replayed():
    citation = {"type": "data-citation", "id": "citation-1", "data": {"chunkId": "x"}}

    [response] = to_model_history([row("assistant", text("Flat [1]."), citation)])

    assert response.parts == [TextPart(content="Flat [1].")]


def test_messages_without_text_and_system_messages_are_skipped():
    rows = [row("assistant", {"type": "data-grounding", "data": {}}), row("system", text("x"))]

    assert to_model_history(rows) == []


def test_only_recent_messages_are_kept():
    rows = [row("user", text(f"q{i}")) for i in range(MAX_HISTORY_MESSAGES + 5)]

    history = to_model_history(rows)

    assert len(history) == MAX_HISTORY_MESSAGES
    assert history[-1].parts[0].content == f"q{MAX_HISTORY_MESSAGES + 4}"
