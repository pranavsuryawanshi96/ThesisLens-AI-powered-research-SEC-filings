"""Live retrieval against the ingested corpus: needs Supabase + OpenAI credentials.

Run: uv run pytest -m integration tests/retrieval
"""

import asyncio

import pytest
from openai import AsyncOpenAI

from app.config import settings
from app.database.session import create_engine
from app.retrieval.retriever import DocumentRetriever
from app.retrieval.types import SearchFilters

pytestmark = pytest.mark.integration


def run(coroutine):
    # psycopg's async driver cannot run on Windows' default Proactor event loop.
    return asyncio.run(coroutine, loop_factory=asyncio.SelectorEventLoop)


async def search(query: str, filters: SearchFilters):
    engine = create_engine()
    try:
        retriever = DocumentRetriever(engine, AsyncOpenAI(api_key=settings.openai_api_key))
        semantic, lexical = await retriever.search_legs(query, filters)
        passages = await retriever.search(query, filters)
        return semantic, lexical, passages
    finally:
        await engine.dispose()


def test_apple_revenue_mix_query_finds_the_net_sales_by_category_passage():
    filters = SearchFilters(tickers=["AAPL"], fiscal_years=[2024])

    semantic, lexical, passages = run(
        search("Apple net sales by category iPhone Services Mac iPad Wearables", filters)
    )

    assert semantic and lexical, "both legs should return candidates"
    assert len(passages) == settings.retrieval_top_k
    assert all(p.ticker == "AAPL" and p.fiscal_year == 2024 for p in passages)
    assert any("iPhone" in p.content and "Wearables" in p.content for p in passages[:5])
    assert passages[0].page is not None
