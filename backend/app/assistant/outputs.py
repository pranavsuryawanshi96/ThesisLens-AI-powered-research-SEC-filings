"""What the agent must return. Passages are not part of it: the model could invent
them, so cited passages are looked up from what the tools actually retrieved."""

from typing import Literal
from uuid import UUID

from pydantic import BaseModel, Field

AnswerStatus = Literal["answered", "insufficient_evidence", "out_of_scope"]


class Citation(BaseModel):
    index: int = Field(description="The n of the [n] marker this citation backs in the answer.")
    chunk_id: UUID = Field(description="The id shown as [chunk:<id>] in the tool results.")
    quote: str = Field(
        description="A short passage copied word for word from that chunk that supports the claim."
    )


class GroundedAnswer(BaseModel):
    status: AnswerStatus = Field(
        description=(
            "answered: the filings support the answer. insufficient_evidence: the filings do not "
            "contain enough to answer (cite whatever partial evidence exists). out_of_scope: the "
            "request is for investment advice or something outside SEC filings."
        )
    )
    answer: str = Field(description="Markdown answer with an [n] marker after every factual claim.")
    citations: list[Citation]
