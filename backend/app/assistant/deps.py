from collections.abc import Callable
from dataclasses import dataclass, field
from uuid import UUID

from app.retrieval.retriever import DocumentRetriever
from app.retrieval.types import RetrievedPassage


@dataclass
class DocumentAgentDeps:
    user_id: UUID
    thread_id: UUID
    retriever: DocumentRetriever
    # Progress messages for the analyst while the agent works ("Searching AAPL FY2024…").
    on_status: Callable[[str], None] = lambda _: None
    # Every chunk a tool showed the model this turn: the only chunks it may cite.
    retrieved: dict[UUID, RetrievedPassage] = field(default_factory=dict)

    def remember(self, passages: list[RetrievedPassage]) -> None:
        for passage in passages:
            for chunk in (passage, *passage.neighbors):
                self.retrieved[chunk.chunk_id] = chunk.model_copy(update={"neighbors": []})
