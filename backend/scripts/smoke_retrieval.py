
from __future__ import annotations

from app.retrieval.retriever import (
    DocumentRetriever,
    format_passages_for_agent,
)
from app.retrieval.types import SearchFilters
from openai import AsyncOpenAI
from app.database.session import create_engine
import asyncio




SMOKE_QUERIES: list[tuple[str, SearchFilters | None]] = [
    (
        "Across Apple's 10-Ks, how did the revenue mix between iPhone, Services, Mac, iPad, and Wearables change?",
        SearchFilters(tickers=["AAPL"]),
    ),
    (
        "How did NVIDIA describe demand drivers and customer concentration for its Data Center business?",
        SearchFilters(tickers=["NVDA"]),
    ),
    (
        "What changed in the way Microsoft describes Azure, AI infrastructure, and cloud capacity constraints?",
        SearchFilters(tickers=["MSFT"]),
    ),
]


async def main() -> None:
    print("Smoke retrieval script started")

    engine = create_engine()
    openai = AsyncOpenAI()
    retriever = DocumentRetriever(engine=engine, openai=openai)
    print("Retriever initialized successfully")

    for query, filters in SMOKE_QUERIES:
        print("\n" + "=" * 80)
        print(f"Query: {query}")

        if filters is not None:
            print(f"Filters: {filters.model_dump_json()}")

        passages = await retriever.search(
            query,
            filters=filters,
            top_k=5,
        )

        print(f"Retrieved passages: {len(passages)}")
        print(format_passages_for_agent(passages))


if __name__ == "__main__":
           asyncio.run(main(), loop_factory=asyncio.SelectorEventLoop)


