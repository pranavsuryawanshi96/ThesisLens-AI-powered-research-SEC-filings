import asyncio
from types import SimpleNamespace
from uuid import uuid4

from app.retrieval import queries
from app.retrieval.types import SearchFilters


class FakeConnection:
    """Records each statement and returns canned rows for the last one."""

    def __init__(self, rows):
        self.rows = rows
        self.calls: list[tuple[str, dict]] = []

    async def execute(self, statement, params=None):
        self.calls.append((str(statement), params or {}))
        return SimpleNamespace(all=lambda: self.rows)


def rows(*scores):
    return [SimpleNamespace(id=uuid4(), score=score) for score in scores]


def test_filter_clause_without_filters_is_empty():
    assert queries.filter_clause(None) == ("", {})
    assert queries.filter_clause(SearchFilters()) == ("", {})


def test_filter_clause_upper_cases_tickers_and_binds_lists():
    sql, params = queries.filter_clause(SearchFilters(tickers=["aapl", "Nvda"], fiscal_years=[2024, 2025]))

    assert "d.ticker = any(:tickers)" in sql
    assert "d.fiscal_year = any(:fiscal_years)" in sql
    assert params == {"tickers": ["AAPL", "NVDA"], "fiscal_years": [2024, 2025]}


def test_vector_literal_is_pgvector_text_format():
    assert queries.vector_literal([0.5, -1.0, 2e-05]) == "[0.5,-1.0,2e-05]"


def test_semantic_search_ranks_rows_and_raises_ef_search():
    conn = FakeConnection(rows(0.9, 0.8))

    hits = asyncio.run(
        queries.semantic_search(conn, [0.1, 0.2], SearchFilters(tickers=["AAPL"]), limit=150)
    )

    settings_sql, settings_params = conn.calls[0]
    assert "hnsw.iterative_scan" in settings_sql
    assert settings_params == {"ef_search": "150"}
    search_sql, search_params = conn.calls[1]
    assert "<=> cast(:query_vector as vector)" in search_sql
    assert "d.ticker = any(:tickers)" in search_sql
    assert search_params == {"tickers": ["AAPL"], "query_vector": "[0.1,0.2]", "limit": 150}
    assert [(hit.rank, hit.score) for hit in hits] == [(1, 0.9), (2, 0.8)]


def test_semantic_search_never_sets_ef_search_below_minimum():
    conn = FakeConnection([])
    asyncio.run(queries.semantic_search(conn, [0.1], None, limit=10))

    assert conn.calls[0][1] == {"ef_search": str(queries.MIN_EF_SEARCH)}


def test_full_text_search_ors_query_terms_and_ranks_rows():
    conn = FakeConnection(rows(0.3, 0.1))

    hits = asyncio.run(
        queries.full_text_search(conn, "iPhone net sales", SearchFilters(fiscal_years=[2023]), limit=50)
    )

    [(sql, params)] = conn.calls
    assert "replace(plainto_tsquery('english', :query)::text, ' & ', ' | ')" in sql
    assert "ts_rank_cd(c.search_vector, q.query, 1)" in sql
    assert "d.fiscal_year = any(:fiscal_years)" in sql
    assert params == {"fiscal_years": [2023], "query": "iPhone net sales", "limit": 50}
    assert [hit.rank for hit in hits] == [1, 2]
