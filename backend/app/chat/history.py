"""Stored chat messages → PydanticAI message history, so follow-up questions have context."""

from typing import Any

from pydantic_ai.messages import (
    ModelMessage,
    ModelRequest,
    ModelResponse,
    TextPart,
    UserPromptPart,
)

from app.chat.messages import text_from_parts

# Enough for follow-ups ("and in 2023?") without replaying a long thread on every turn.
MAX_HISTORY_MESSAGES = 10


def to_model_history(rows: list[dict[str, Any]]) -> list[ModelMessage]:
    """Only the text is replayed: earlier citations can't be re-cited without re-retrieval."""
    history: list[ModelMessage] = []
    for row in rows[-MAX_HISTORY_MESSAGES:]:
        text = text_from_parts(row["parts"])
        if not text:
            continue
        if row["role"] == "user":
            history.append(ModelRequest(parts=[UserPromptPart(content=text)]))
        elif row["role"] == "assistant":
            history.append(ModelResponse(parts=[TextPart(content=text)]))
    return history
