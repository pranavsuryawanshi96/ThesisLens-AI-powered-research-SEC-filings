"""AI SDK UIMessage wire format at the HTTP boundary."""

from typing import Any, Literal
from uuid import UUID

from pydantic import AliasChoices, BaseModel, Field, model_validator

TITLE_MAX_LENGTH = 80


class UIMessage(BaseModel):
    id: str
    role: Literal["user", "assistant", "system"]
    # Stored verbatim so history reloads render exactly as the client sent them.
    parts: list[dict[str, Any]]


class ChatStreamRequest(BaseModel):
    # useChat always sends its chat `id`; an explicit `threadId` in the request body wins.
    thread_id: UUID = Field(validation_alias=AliasChoices("threadId", "id"))
    messages: list[UIMessage] = Field(min_length=1)

    @model_validator(mode="after")
    def _last_message_is_user_text(self) -> "ChatStreamRequest":
        last = self.messages[-1]
        if last.role != "user":
            raise ValueError("the last message must be a user message")
        if not text_from_parts(last.parts).strip():
            raise ValueError("the user message has no text")
        return self

    @property
    def user_message(self) -> UIMessage:
        return self.messages[-1]


def text_from_parts(parts: list[dict[str, Any]]) -> str:
    return "".join(
        part["text"] for part in parts if part.get("type") == "text" and isinstance(part.get("text"), str)
    )


def title_from_text(text: str) -> str:
    first_line = text.strip().splitlines()[0].strip()
    if len(first_line) <= TITLE_MAX_LENGTH:
        return first_line
    return first_line[: TITLE_MAX_LENGTH - 1].rstrip() + "…"
