"""Encoding for the AI SDK UI message stream protocol (v1): server-sent events of JSON parts."""

import json
from typing import Any

# useChat's DefaultChatTransport parses the body as this protocol.
STREAM_HEADERS = {
    "x-vercel-ai-ui-message-stream": "v1",
    "Cache-Control": "no-cache",
    # Stop proxies (Railway's included) from buffering the stream into one chunk.
    "X-Accel-Buffering": "no",
}

DONE = "data: [DONE]\n\n"


def sse(event: dict[str, Any]) -> str:
    return f"data: {json.dumps(event, ensure_ascii=False)}\n\n"


def text_deltas(text: str) -> list[str]:
    """Split text into word-sized deltas, keeping the whitespace so they rejoin exactly."""
    words = text.split(" ")
    return [word + " " for word in words[:-1]] + [words[-1]]
