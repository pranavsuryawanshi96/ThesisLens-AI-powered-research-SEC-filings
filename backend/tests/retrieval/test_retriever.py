import asyncio
from contextlib import asynccontextmanager
from datetime import date
from uuid import UUID, uuid4

import pytest

from app.config import settings
from app.retrieval import retriever as retriever_module
from app.retrieval.retriever import DocumentRetriever, format_passages_for_agent
from app.retrieval.types import RankedChunkHit, RetrievedPassage, SearchFilters

DOCUMENT_ID = uuid4()


def passage(chunk_index: int, chunk_id: UUID | None = None, **overrides) -> RetrievedPassage:
    fields = {
        "chunk_id": chunk_id or uuid4(),
        "document_id": DOCUMENT_ID,
        "chunk_index": chunk_index,
        "content": f"chunk {chunk_index} text",
        "page": 40 + chunk_index,
        "page_end": 40 + chunk_index,
        "section": "Item 7 > Net sales",
        "ticker": "AAPL",
        "company_name": "Apple Inc.",
        "filing_type": "10-K",
        "filing_date": date(2024, 11, 1),
        "fiscal_year": 2024,
        "accession_number": "0000320193-24-000123",
        "source_url": "https://www.sec.gov/example",
    }
    return RetrievedPassage(**(fields | overrides))


def hits(*chunk_ids: UUID) -> list[RankedChunkHit]:
    return [RankedChunkHit(chunk_id=c, rank=r, score=1.0 / r) for r, c in enumerate(chunk_ids, start=1)]


class FakeEngine:
    def __init__(self):
        self.connections = 0

    @asynccontextmanager
    async def connect(self):
        self.connections += 1
        yield object()


class FakeCorpus:
    """Stands in for queries + documents: legs return fixed rankings, lookups read a dict."""

    def __init__(self, chunks: list[RetrievedPassage], semantic: list[UUID], lexical: list[UUID]):
        self.chunks = {c.chunk_id: c for c in chunks}
        self.semantic = semantic
        self.lexical = lexical
        self.calls: dict[str, list] = {"embed": [], "semantic": [], "lexical": []}

    async def embed_query(self, client, text):
        self.calls["embed"].append(text)
        return [0.0] * 3

    async def semantic_search(self, conn, vector, filters, limit):
        self.calls["semantic"].append((filters, limit))
        return hits(*self.semantic)

    async def full_text_search(self, conn, query, filters, limit):
        self.calls["lexical"].append((query, filters, limit))
        return hits(*self.lexical)

    async def get_chunks_by_ids(self, conn, chunk_ids):
        # Reversed, like a database that ignores the requested order.
        return {c: self.chunks[c] for c in reversed(chunk_ids) if c in self.chunks}

    async def get_surrounding_chunks(self, conn, chunk_ids, radius):
        result = {}
        for chunk_id in chunk_ids:
            anchor = self.chunks[chunk_id]
            result[chunk_id] = sorted(
                (
                    c
                    for c in self.chunks.values()
                    if c.chunk_id != chunk_id and abs(c.chunk_index - anchor.chunk_index) <= radius
                ),
                key=lambda c: c.chunk_index,
            )
        return result


@pytest.fixture
def corpus_factory(monkeypatch):
    def install(chunks, semantic, lexical) -> FakeCorpus:
        corpus = FakeCorpus(chunks, semantic, lexical)
        monkeypatch.setattr(retriever_module, "embed_query", corpus.embed_query)
        monkeypatch.setattr(retriever_module.queries, "semantic_search", corpus.semantic_search)
        monkeypatch.setattr(retriever_module.queries, "full_text_search", corpus.full_text_search)
        monkeypatch.setattr(retriever_module.documents, "get_chunks_by_ids", corpus.get_chunks_by_ids)
        monkeypatch.setattr(
            retriever_module.documents, "get_surrounding_chunks", corpus.get_surrounding_chunks
        )
        return corpus

    return install


def run_search(**kwargs) -> list[RetrievedPassage]:
    retriever = DocumentRetriever(FakeEngine(), openai=None)
    return asyncio.run(retriever.search("apple iphone revenue", **kwargs))


def test_search_embeds_once_and_sends_same_filters_to_both_legs(corpus_factory):
    chunks = [passage(i) for i in range(3)]
    corpus = corpus_factory(chunks, [chunks[0].chunk_id], [chunks[1].chunk_id])
    filters = SearchFilters(tickers=["AAPL"], fiscal_years=[2024])

    run_search(filters=filters, neighbor_radius=0)

    assert corpus.calls["embed"] == ["apple iphone revenue"]
    assert corpus.calls["semantic"] == [(filters, settings.retrieval_candidate_k)]
    assert corpus.calls["lexical"] == [("apple iphone revenue", filters, settings.retrieval_candidate_k)]


def test_search_returns_fused_order_with_leg_ranks(corpus_factory):
    a, b, c = (passage(i * 10) for i in range(3))
    # b is in both legs, so it fuses to the top even though the DB returns rows unordered.
    corpus_factory([a, b, c], [a.chunk_id, b.chunk_id], [b.chunk_id, c.chunk_id])

    results = run_search(neighbor_radius=0)

    assert [r.chunk_id for r in results] == [b.chunk_id, a.chunk_id, c.chunk_id]
    assert (results[0].semantic_rank, results[0].lexical_rank) == (2, 1)
    assert (results[1].semantic_rank, results[1].lexical_rank) == (1, None)
    assert results[0].fusion_score > results[1].fusion_score


def test_search_truncates_to_top_k(corpus_factory):
    chunks = [passage(i * 10) for i in range(5)]
    corpus_factory(chunks, [c.chunk_id for c in chunks], [])

    assert len(run_search(top_k=2, neighbor_radius=0)) == 2


def test_search_attaches_neighbors_without_repeating_chunks(corpus_factory):
    # Hits at indexes 2 and 4 both border chunk 3; it goes only to the higher-ranked hit.
    chunks = {i: passage(i) for i in range(1, 6)}
    corpus_factory(list(chunks.values()), [chunks[2].chunk_id, chunks[4].chunk_id], [])

    first, second = run_search(neighbor_radius=1)

    assert [n.chunk_index for n in first.neighbors] == [1, 3]
    assert [n.chunk_index for n in second.neighbors] == [5]


def test_neighbor_that_is_itself_a_hit_is_not_repeated(corpus_factory):
    chunks = {i: passage(i) for i in range(3)}
    corpus_factory(list(chunks.values()), [chunks[1].chunk_id, chunks[2].chunk_id], [])

    first, second = run_search(neighbor_radius=1)

    assert [n.chunk_index for n in first.neighbors] == [0]
    assert second.neighbors == []


def test_search_with_no_hits_returns_empty(corpus_factory):
    corpus_factory([], [], [])

    assert run_search() == []


def test_read_surrounding_chunks_returns_window_in_filing_order(corpus_factory):
    chunks = {i: passage(i) for i in range(5)}
    corpus_factory(list(chunks.values()), [], [])
    retriever = DocumentRetriever(FakeEngine(), openai=None)

    window = asyncio.run(retriever.read_surrounding_chunks(chunks[2].chunk_id, radius=1))

    assert [p.chunk_index for p in window] == [1, 2, 3]


def test_read_chunk_missing_returns_none(corpus_factory):
    corpus_factory([], [], [])
    retriever = DocumentRetriever(FakeEngine(), openai=None)

    assert asyncio.run(retriever.read_chunk(uuid4())) is None
    assert asyncio.run(retriever.read_surrounding_chunks(uuid4())) == []


def test_format_passages_heads_every_chunk_with_its_citable_id():
    hit = passage(2, neighbors=[passage(1), passage(3, page=43, page_end=44)])

    text = format_passages_for_agent([hit])

    assert text.startswith("## Result 1")
    assert f"[chunk:{hit.chunk_id}] AAPL 10-K FY2024 p.42 · Item 7 > Net sales (match)" in text
    for neighbor in hit.neighbors:
        assert f"[chunk:{neighbor.chunk_id}]" in text
    assert "p.43-44" in text
    # Context reads in filing order around the match.
    assert text.index("chunk 1 text") < text.index("chunk 2 text") < text.index("chunk 3 text")


def test_format_passages_empty():
    assert format_passages_for_agent([]) == "No matching passages found."
