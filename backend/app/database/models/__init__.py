"""SQLAlchemy models. Import `Base.metadata` from here so Alembic sees every table."""

from app.database.models.base import EMBEDDING_DIMENSIONS, Base
from app.database.models.chats import ChatMessage, ChatThread, MessageCitation
from app.database.models.documents import DocumentChunk, SourceDocument
from app.database.models.users import User

__all__ = [
    "EMBEDDING_DIMENSIONS",
    "Base",
    "ChatMessage",
    "ChatThread",
    "DocumentChunk",
    "MessageCitation",
    "SourceDocument",
    "User",
]
