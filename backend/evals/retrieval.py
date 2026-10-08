"""Compare semantic-only, full-text-only, and hybrid (RRF) retrieval on labeled queries.

Run from backend/ once the corpus is ingested:
  uv run python -m evals.retrieval                                  # score all labeled queries
  uv run python -m evals.retrieval --query "AWS operating income" --ticker AMZN --year 2023
"""

import argparse
import asyncio
import json
import statistics
from pathlib import Path
from typing import Any
from uuid import UUID

from openai import AsyncOpenAI

from app.config import settings
from app.database import documents
from app.database.session import create_engine
from app.retrieval.fusion import reciprocal_rank_fusion
from app.retrieval.retriever import DocumentRetriever
from app.retrieval.types import RetrievedPassage, SearchFilters

QUERIES_FILE = Path(__file__).with_name("retrieval_queries.json")
K = 10
METHODS = ("Semantic", "Full-text", "Hybrid (RRF)")


async def rank_methods(
    retriever: DocumentRetriever, query: str, filters: SearchFilters
) -> tuple[dict[str, list[UUID]], dict[UUID, RetrievedPassage]]:
    """Top-K chunk ids per method, plus the chunks themselves for judging/printing."""
    semantic, lexical = await retriever.search_legs(query, filters)
    semantic_ids = [hit.chunk_id for hit in semantic]
    lexical_ids = [hit.chunk_id for hit in lexical]
    fused = reciprocal_rank_fusion([semantic_ids, lexical_ids], k=settings.retrieval_rrf_k)
    rankings = {
        "Semantic": semantic_ids[:K],
        "Full-text": lexical_ids[:K],
        "Hybrid (RRF)": [chunk_id for chunk_id, _ in fused[:K]],
    }
    all_ids = list({chunk_id for ids in rankings.values() for chunk_id in ids})
    async with retriever.engine.connect() as conn:
        chunks = await documents.get_chunks_by_ids(conn, all_ids)
    return rankings, chunks


def is_relevant(passage: RetrievedPassage, label: dict[str, Any]) -> bool:
    content = passage.content.lower()
    return all(phrase.lower() in content for phrase in label["all_of"])


def score(relevance: list[bool]) -> dict[str, float]:
    first = next((rank for rank, hit in enumerate(relevance, start=1) if hit), None)
    return {
        "hit@5": float(any(relevance[:5])),
        "mrr@10": 1 / first if first else 0.0,
        "p@10": sum(relevance) / K,
    }


async def evaluate(retriever: DocumentRetriever) -> None:
    labels = json.loads(QUERIES_FILE.read_text(encoding="utf-8"))["queries"]
    results: dict[str, list[dict[str, float]]] = {method: [] for method in METHODS}
    for label in labels:
        filters = SearchFilters(tickers=label["tickers"], fiscal_years=label["fiscal_years"])
        rankings, chunks = await rank_methods(retriever, label["query"], filters)
        line = []
        for method in METHODS:
            relevance = [is_relevant(chunks[c], label) for c in rankings[method] if c in chunks]
            results[method].append(score(relevance))
            line.append(f"{method.split()[0][:4]}={results[method][-1]['mrr@10']:.2f}")
        print(f"  Q{label['brief']:<2} {label['query'][:60]:<60} mrr {' '.join(line)}")

    print(f"\n{len(labels)} queries, top {K}")
    print(f"  {'Method':<14} {'Hit@5':>7} {'MRR@10':>7} {'P@10':>7}")
    for method, scores in results.items():
        means = {metric: statistics.mean(s[metric] for s in scores) for metric in scores[0]}
        print(f"  {method:<14} {means['hit@5']:>7.2f} {means['mrr@10']:>7.2f} {means['p@10']:>7.2f}")


async def show(retriever: DocumentRetriever, query: str, filters: SearchFilters) -> None:
    rankings, chunks = await rank_methods(retriever, query, filters)
    print(f"Query: {query}")
    for method in METHODS:
        print(f"\n{method}")
        for rank, chunk_id in enumerate(rankings[method][:5], start=1):
            passage = chunks[chunk_id]
            snippet = " ".join(passage.content.split())[:90]
            print(f"  {rank}. {passage.label}  {passage.section or ''}\n     {snippet}")


async def main(args: argparse.Namespace) -> None:
    engine = create_engine()
    retriever = DocumentRetriever(engine, AsyncOpenAI(api_key=settings.openai_api_key))
    try:
        if args.query:
            filters = SearchFilters(
                tickers=[args.ticker] if args.ticker else None,
                fiscal_years=[args.year] if args.year else None,
            )
            await show(retriever, args.query, filters)
        else:
            await evaluate(retriever)
    finally:
        await engine.dispose()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--query", help="print the top 5 per method for one query instead of scoring")
    parser.add_argument("--ticker")
    parser.add_argument("--year", type=int)
    # psycopg's async driver cannot run on Windows' default Proactor event loop.
    asyncio.run(main(parser.parse_args()), loop_factory=asyncio.SelectorEventLoop)
