"""The trust contract, enforced in code: every citation points at a passage retrieved
this turn and quotes it verbatim, and every [n] in the answer has a citation.

Independent of PydanticAI so it can be unit-tested and re-run as a final gate.
Error messages are written for the model, which gets them back as retry feedback.
"""

import re
from collections import Counter
from collections.abc import Mapping
from uuid import UUID

from app.assistant.outputs import GroundedAnswer
from app.retrieval.types import RetrievedPassage

# "[1]" or "[1, 3]".
MARKER = re.compile(r"\[(\d+(?:\s*,\s*\d+)*)\]")
ELLIPSIS = re.compile(r"\.\.\.|…")
# Shorter quotes ("Net sales") would match almost any chunk and prove nothing.
MIN_QUOTE_CHARS = 12

# Typography that differs between the filing text and what a model types back.
# Table pipes go too: chunks hold Markdown tables, and quoting a row shouldn't need them.
NORMALIZE = str.maketrans(
    {
        "‘": "'", "’": "'", "“": '"', "”": '"',
        "–": "-", "—": "-", "−": "-",
        " ": " ", "|": " ",
    }
)


def normalize(text: str) -> str:
    return " ".join(text.translate(NORMALIZE).casefold().split())


def marker_indexes(answer: str) -> list[int]:
    return [int(n) for group in MARKER.findall(answer) for n in group.split(",")]


def quote_in_passage(quote: str, passage: RetrievedPassage) -> bool:
    """Each ellipsis-separated piece of the quote must appear verbatim in the chunk."""
    content = normalize(passage.content)
    pieces = [normalize(piece) for piece in ELLIPSIS.split(quote)]
    pieces = [piece for piece in pieces if piece]
    return bool(pieces) and all(piece in content for piece in pieces)


def validate_grounding(
    answer: GroundedAnswer, retrieved: Mapping[UUID, RetrievedPassage]
) -> list[str]:
    """All violations, empty when the answer is grounded."""
    errors: list[str] = []
    if not answer.answer.strip():
        errors.append("The answer text is empty.")
    if answer.status == "answered" and not answer.citations:
        errors.append(
            "An answered question needs at least one citation. If the filings do not support "
            "an answer, use status insufficient_evidence."
        )

    counts = Counter(citation.index for citation in answer.citations)
    for index, count in sorted(counts.items()):
        if count > 1:
            errors.append(f"Citation index {index} is used by {count} citations; indexes must be unique.")

    markers = set(marker_indexes(answer.answer))
    for index in sorted(markers - counts.keys()):
        errors.append(f"The answer contains [{index}] but there is no citation with index {index}.")
    for index in sorted(counts.keys() - markers):
        errors.append(f"Citation {index} is never referenced as [{index}] in the answer.")

    for citation in answer.citations:
        passage = retrieved.get(citation.chunk_id)
        if passage is None:
            errors.append(
                f"Citation {citation.index} cites chunk {citation.chunk_id}, which was not returned "
                "by a tool in this conversation turn. Only cite chunks you retrieved."
            )
        elif len(normalize(citation.quote)) < MIN_QUOTE_CHARS:
            errors.append(f"Citation {citation.index}'s quote is too short to verify; quote a full phrase.")
        elif not quote_in_passage(citation.quote, passage):
            errors.append(
                f"Citation {citation.index}'s quote does not appear in chunk {citation.chunk_id}. "
                "Copy the quote word for word from that chunk."
            )
    return errors
