import uuid
from datetime import date
from typing import Any

from pgvector.sqlalchemy import Vector
from sqlalchemy import (
    Computed,
    Date,
    ForeignKey,
    Index,
    Integer,
    Text,
    UniqueConstraint,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB, TSVECTOR, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database.models.base import EMBEDDING_DIMENSIONS, Base, CreatedAtMixin


class SourceDocument(CreatedAtMixin, Base):
    """One SEC filing, stored as normalized Markdown so it can be re-chunked and cited."""

    __tablename__ = "source_documents"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")
    )
    ticker: Mapped[str] = mapped_column(Text)
    company_name: Mapped[str | None] = mapped_column(Text)
    cik: Mapped[str] = mapped_column(Text)
    filing_type: Mapped[str] = mapped_column(Text)
    filing_date: Mapped[date] = mapped_column(Date)
    report_date: Mapped[date | None] = mapped_column(Date)
    fiscal_year: Mapped[int] = mapped_column(Integer)
    # Natural key from EDGAR; ingestion uses it to skip already-loaded filings.
    accession_number: Mapped[str] = mapped_column(Text, unique=True)
    source_url: Mapped[str] = mapped_column(Text)
    content_markdown: Mapped[str] = mapped_column(Text)
    meta: Mapped[dict[str, Any]] = mapped_column(
        "metadata", JSONB, server_default=text("'{}'::jsonb")
    )

    chunks: Mapped[list["DocumentChunk"]] = relationship(
        back_populates="document", cascade="all, delete-orphan", passive_deletes=True
    )

    __table_args__ = (Index(None, "ticker", "fiscal_year"),)


class DocumentChunk(CreatedAtMixin, Base):
    """A retrieval-ready passage with its embedding and full-text search vector."""

    __tablename__ = "document_chunks"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")
    )
    document_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("source_documents.id", ondelete="CASCADE")
    )
    chunk_index: Mapped[int] = mapped_column(Integer)
    page: Mapped[int | None] = mapped_column(Integer)
    section: Mapped[str | None] = mapped_column(Text)
    content: Mapped[str] = mapped_column(Text)
    token_count: Mapped[int] = mapped_column(Integer)
    # Nullable so chunks can be written before their embedding batch returns.
    embedding: Mapped[list[float] | None] = mapped_column(Vector(EMBEDDING_DIMENSIONS))
    search_vector: Mapped[str] = mapped_column(
        TSVECTOR, Computed("to_tsvector('english', content)", persisted=True)
    )
    # Ticker, company, filing type/date, year, accession, source offsets —
    # denormalized so retrieval results can be cited without a join.
    meta: Mapped[dict[str, Any]] = mapped_column(
        "metadata", JSONB, server_default=text("'{}'::jsonb")
    )

    document: Mapped[SourceDocument] = relationship(back_populates="chunks")

    __table_args__ = (
        UniqueConstraint("document_id", "chunk_index"),
        Index(
            "ix_document_chunks_embedding_hnsw",
            "embedding",
            postgresql_using="hnsw",
            postgresql_with={"m": 16, "ef_construction": 64},
            postgresql_ops={"embedding": "vector_cosine_ops"},
        ),
        Index(
            "ix_document_chunks_search_vector_gin",
            "search_vector",
            postgresql_using="gin",
        ),
    )
