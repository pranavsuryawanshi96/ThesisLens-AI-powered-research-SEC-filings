import asyncio

from app.database import documents
from app.database.session import create_engine
from app.retrieval import queries
from app.retrieval.retriever import format_chunk
from app.retrieval.types import SearchFilters

SMOKE_QUERIES = [
    ("iPhone Services Mac iPad Wearables net sales", SearchFilters(tickers=["AAPL"])),
    ("Data Center demand customer concentration", SearchFilters(tickers=["NVDA"])),
    ("Azure AI infrastructure capacity constraints", SearchFilters(tickers=["MSFT"])),
]


async def main() -> None:
    engine = create_engine()
    try:
        for query, filters in SMOKE_QUERIES:
            print("\n" + "=" * 80)
            print(f"Query: {query}")
            async with engine.connect() as conn:
                hits = await queries.full_text_search(conn, query, filters, 5)
                chunks = await documents.get_chunks_by_ids(conn, [h.chunk_id for h in hits])
            print(f"Retrieved passages: {len(hits)}")
            for hit in hits:
                print(f"\n#{hit.rank} score={hit.score:.4f}")
                print(format_chunk(chunks[hit.chunk_id])[:600])
    finally:
        await engine.dispose()


if __name__ == "__main__":
    asyncio.run(main(), loop_factory=asyncio.SelectorEventLoop)
