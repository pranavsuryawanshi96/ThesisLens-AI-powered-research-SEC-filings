from uuid import uuid4

import pytest
from pydantic import ValidationError

from app.chat.messages import ChatStreamRequest, text_from_parts, title_from_text


def user_message(text: str) -> dict:
    return {"id": "m1", "role": "user", "parts": [{"type": "text", "text": text}]}


def test_text_from_parts_joins_text_parts_only():
    parts = [
        {"type": "text", "text": "Hello "},
        {"type": "file", "url": "x"},
        {"type": "text", "text": "world"},
    ]
    assert text_from_parts(parts) == "Hello world"


def test_title_from_text_uses_first_line_and_truncates():
    assert title_from_text("  Apple revenue mix?\nmore detail") == "Apple revenue mix?"
    long_title = title_from_text("word " * 40)
    assert len(long_title) == 80
    assert long_title.endswith("…")


def test_stream_request_accepts_ai_sdk_id_or_thread_id():
    thread_id = uuid4()
    by_id = ChatStreamRequest.model_validate({"id": str(thread_id), "messages": [user_message("hi")]})
    by_thread_id = ChatStreamRequest.model_validate(
        {"id": "chat-abc", "threadId": str(thread_id), "messages": [user_message("hi")]}
    )
    assert by_id.thread_id == by_thread_id.thread_id == thread_id


@pytest.mark.parametrize(
    "messages",
    [
        [],
        [{"id": "a1", "role": "assistant", "parts": [{"type": "text", "text": "hi"}]}],
        [user_message("   ")],
    ],
)
def test_stream_request_rejects_missing_or_empty_user_turn(messages):
    with pytest.raises(ValidationError):
        ChatStreamRequest.model_validate({"threadId": str(uuid4()), "messages": messages})
