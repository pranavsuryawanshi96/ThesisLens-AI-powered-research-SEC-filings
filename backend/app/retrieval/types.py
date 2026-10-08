"""Retrieval models shared by the retriever, its tests, and the agent tools."""

from datetime import date
from uuid import UUID

from pydantic import BaseModel


class SearchFilters(BaseModel):
    # Lists, so comparison questions can scope one search to several companies or years.
    tickers: list[str] | None = None
    fiscal_years: list[int] | None = None


class RankedChunkHit(BaseModel):
    """One result from a single search leg, before fusion."""

    chunk_id: UUID
    rank: int
    score: float


class RetrievedPassage(BaseModel):
    chunk_id: UUID
    document_id: UUID
    chunk_index: int
    content: str
    page: int | None
    page_end: int | None
    section: str | None
    # Filing metadata, so the passage can be cited without another lookup.
    ticker: str
    company_name: str | None
    filing_type: str
    filing_date: date
    fiscal_year: int
    accession_number: str
    source_url: str
    # None for passages read directly or attached as neighbors rather than ranked.
    fusion_score: float | None = None
    semantic_rank: int | None = None
    lexical_rank: int | None = None
    # Surrounding chunks from the same filing, ordered by chunk_index; never nested.
    neighbors: list["RetrievedPassage"] = []

    @property
    def label(self) -> str:
        pages = f"p.{self.page}" if self.page is not None else "p.?"
        if self.page_end is not None and self.page_end != self.page:
            pages += f"-{self.page_end}"
        return f"{self.ticker} {self.filing_type} FY{self.fiscal_year} {pages}"
