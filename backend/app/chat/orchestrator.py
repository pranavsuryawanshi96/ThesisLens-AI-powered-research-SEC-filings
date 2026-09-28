"""One chat turn end-to-end: stream the assistant reply, then persist the turn.

The reply is a stub until the grounded agent lands; the stream and persistence
contract around it is what the frontend is built against.
"""

from collections.abc import AsyncIterator
from typing import Any
from uuid import UUID, uuid4

from supabase import AsyncClient

from app.chat.messages import UIMessage, text_from_parts, title_from_text
from app.chat.streaming import DONE, sse, text_deltas
from app.database import chats

STUB_REPLY = (
    "This is a stubbed response. Grounded answers with citations from the filings "
    "will replace it once retrieval is in place. You asked: "
)


async def stream_stub_turn(
    service: AsyncClient, thread: dict[str, Any], user_message: UIMessage
) -> AsyncIterator[str]:
    question = text_from_parts(user_message.parts)
    reply = STUB_REPLY + question
    message_id = str(uuid4())
    text_id = str(uuid4())

    yield sse({"type": "start", "messageId": message_id})
    yield sse({"type": "text-start", "id": text_id})
    for delta in text_deltas(reply):
        yield sse({"type": "text-delta", "id": text_id, "delta": delta})
    yield sse({"type": "text-end", "id": text_id})

    # Persist only once the whole reply is out; a client that disconnects earlier
    # cancels this generator and nothing is saved.
    title = title_from_text(question) if thread["title"] == chats.DEFAULT_THREAD_TITLE else None
    await chats.save_turn(
        service,
        UUID(thread["id"]),
        [
            {"role": "user", "content": question, "parts": user_message.parts},
            {
                "id": message_id,
                "role": "assistant",
                "content": reply,
                "parts": [{"type": "text", "text": reply}],
            },
        ],
        title,
    )

    yield sse({"type": "finish"})
    yield DONE
