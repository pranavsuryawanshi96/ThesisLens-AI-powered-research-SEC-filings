"""The two ranked search legs over document_chunks: pgvector and Postgres full-text."""

from typing import Any

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncConnection

from app.retrieval.types import RankedChunkHit, SearchFilters

# HNSW returns at most ef_search rows (pgvector default 40), so it must exceed the limit.
MIN_EF_SEARCH = 100


def filter_clause(filters: SearchFilters | None) -> tuple[str, dict[str, Any]]:
    """SQL conditions on source_documents `d`, ANDed onto a WHERE clause."""
    clauses: list[str] = []
    params: dict[str, Any] = {}
    if filters and filters.tickers:
        clauses.append("and d.ticker = any(:tickers)")
        params["tickers"] = [ticker.upper() for ticker in filters.tickers]
    if filters and filters.fiscal_years:
        clauses.append("and d.fiscal_year = any(:fiscal_years)")
        params["fiscal_years"] = filters.fiscal_years
    return " ".join(clauses), params


def vector_literal(vector: list[float]) -> str:
    return "[" + ",".join(repr(x) for x in vector) + "]"


async def semantic_search(
    conn: AsyncConnection, query_vector: list[float], filters: SearchFilters | None, limit: int
) -> list[RankedChunkHit]:
    where, params = filter_clause(filters)
    # Without iterative scans, a filtered HNSW search filters the ef_search
    # candidates afterwards and silently returns fewer than `limit` rows (pgvector >= 0.8).
    # Both settings are transaction-local; the connection's implicit transaction ends on close.
    await conn.execute(
        text(
            "select set_config('hnsw.ef_search', :ef_search, true), "
            "set_config('hnsw.iterative_scan', 'relaxed_order', true)"
        ),
        {"ef_search": str(max(MIN_EF_SEARCH, limit))},
    )
    # relaxed_order may return rows slightly out of order, hence the re-sort.
    sql = f"""
        with candidates as materialized (
            select c.id, c.embedding <=> cast(:query_vector as vector) as distance
            from document_chunks c
            join source_documents d on d.id = c.document_id
            where c.embedding is not null {where}
            order by distance
            limit :limit
        )
        select id, 1 - distance as score from candidates order by distance, id
    """
    result = await conn.execute(
        text(sql), {**params, "query_vector": vector_literal(query_vector), "limit": limit}
    )
    return ranked(result.all())


async def full_text_search(
    conn: AsyncConnection, query: str, filters: SearchFilters | None, limit: int
) -> list[RankedChunkHit]:
    where, params = filter_clause(filters)
    # plainto_tsquery ANDs every word, so a full analyst question would match almost
    # nothing. Swapping & for | matches any term, and ts_rank_cd ranks chunks that
    # contain more of them higher -- closer to how BM25 treats a query. Normalization 1
    # divides by log(document length), so long chunks don't win just by size.
    sql = f"""
        with q as (
            select replace(plainto_tsquery('english', :query)::text, ' & ', ' | ')::tsquery as query
        )
        select c.id, ts_rank_cd(c.search_vector, q.query, 1) as score
        from document_chunks c
        join source_documents d on d.id = c.document_id
        cross join q
        where c.search_vector @@ q.query {where}
        order by score desc, c.id
        limit :limit
    """
    result = await conn.execute(text(sql), {**params, "query": query, "limit": limit})
    return ranked(result.all())


def ranked(rows: Any) -> list[RankedChunkHit]:
    return [
        RankedChunkHit(chunk_id=row.id, rank=rank, score=row.score)
        for rank, row in enumerate(rows, start=1)
    ]
