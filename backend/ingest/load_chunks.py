"""Chunk the SEC HTML corpus, embed each chunk, and write document_chunks.

Run from backend/:
  uv run python -m ingest.load_chunks --dry-run [--preview chunks.jsonl]   # no API, no DB
  uv run python -m ingest.load_chunks --one --ticker AAPL --year 2025      # embed + insert 1 chunk
  uv run python -m ingest.load_chunks                                      # full corpus

A filing counts as done once source_documents.metadata.chunk_count is set; done filings
are skipped. Any other chunks a filing has (an interrupted run, the --one test) are
deleted and rebuilt.
"""

import argparse
import asyncio
import json
import re
import statistics
import sys
from pathlib import Path
from typing import Any

import psycopg
from docling_core.transforms.chunker import HierarchicalChunker
from openai import AsyncOpenAI
from supabase import AsyncClient

from app.config import BACKEND_DIR, settings
from app.database.supabase import create_service_client
from ingest.chunking import (
    MAX_TOKENS,
    Chunk,
    MarkdownTableSerializerProvider,
    chunk_document,
    chunk_filing,
    get_chunker,
    prepare_document,
)
from ingest.embedding import embed_texts

DOWNLOADS_DIR = BACKEND_DIR.parent / "data" / "downloads"
# The API rejects inputs over 8191 tokens; MAX_TOKENS is our own, lower target.
MAX_INPUT_TOKENS = 8191
INSERT_BATCH_SIZE = 50
DOCUMENT_COLUMNS = (
    "id, ticker, company_name, filing_type, filing_date, fiscal_year, "
    "accession_number, source_url, metadata"
)


def select_filings(ticker: str | None, year: int | None) -> list[dict[str, Any]]:
    manifest = json.loads((DOWNLOADS_DIR / "manifest.json").read_text(encoding="utf-8"))
    return [
        filing
        for filing in manifest["filings"]
        if (ticker is None or filing["ticker"] == ticker.upper())
        and (year is None or filing_path(filing).parent.name == str(year))
    ]


def filing_path(filing: dict[str, Any]) -> Path:
    # download.py writes local_path with the OS separator.
    return DOWNLOADS_DIR / filing["local_path"].replace("\\", "/")


def chunk_row(document: dict[str, Any], chunk: Chunk, embedding: list[float]) -> dict[str, Any]:
    return {
        "document_id": document["id"],
        "chunk_index": chunk.index,
        "page": chunk.page,
        "section": chunk.section,
        "content": chunk.content,
        "token_count": chunk.token_count,
        "embedding": embedding,
        "metadata": {
            "ticker": document["ticker"],
            "company_name": document["company_name"],
            "filing_type": document["filing_type"],
            "filing_date": document["filing_date"],
            "fiscal_year": document["fiscal_year"],
            "accession_number": document["accession_number"],
            "source_url": document["source_url"],
            "headings": chunk.headings,
            "page_end": chunk.page_end,
        },
    }


async def fetch_document(client: AsyncClient, accession_number: str) -> dict[str, Any]:
    response = (
        await client.table("source_documents")
        .select(DOCUMENT_COLUMNS)
        .eq("accession_number", accession_number)
        .limit(1)
        .execute()
    )
    if not response.data:
        raise SystemExit(f"{accession_number} is not in source_documents; run ingest.load_documents first")
    return response.data[0]


async def insert_chunks(
    client: AsyncClient, openai: AsyncOpenAI, document: dict[str, Any], chunks: list[Chunk]
) -> None:
    oversized = [chunk.index for chunk in chunks if chunk.token_count > MAX_INPUT_TOKENS]
    if oversized:
        raise ValueError(f"chunks {oversized} exceed the embedding input limit")
    for start in range(0, len(chunks), INSERT_BATCH_SIZE):
        batch = chunks[start : start + INSERT_BATCH_SIZE]
        embeddings = await embed_texts(openai, [chunk.embed_text for chunk in batch])
        rows = [chunk_row(document, chunk, embedding) for chunk, embedding in zip(batch, embeddings, strict=True)]
        await client.table("document_chunks").insert(rows).execute()
        print(f"  {start + len(batch)}/{len(chunks)} chunks written")


async def delete_chunks(client: AsyncClient, document_id: str) -> None:
    await client.table("document_chunks").delete().eq("document_id", document_id).execute()


def dry_run(filings: list[dict[str, Any]], preview: Path | None) -> None:
    preview_file = preview.open("w", encoding="utf-8") if preview else None
    total_chunks = total_tokens = 0
    for filing in filings:
        path = filing_path(filing)
        doc, pages = prepare_document(path.read_text(encoding="utf-8"), name=path.stem)
        hierarchical = sum(
            1 for _ in HierarchicalChunker(serializer_provider=MarkdownTableSerializerProvider()).chunk(doc)
        )
        hybrid = sum(1 for _ in get_chunker().chunk(doc))
        chunks = chunk_document(doc, pages)
        tokens = [chunk.token_count for chunk in chunks]
        total_chunks += len(chunks)
        total_tokens += sum(tokens)
        print(
            f"{filing['ticker']:5} {path.parent.name}  pages={max(pages.values(), default=0):3}  "
            f"hierarchical={hierarchical:5}  hybrid={hybrid:4}  kept={len(chunks):4}  "
            f"tokens min/avg/max={min(tokens)}/{statistics.mean(tokens):.0f}/{max(tokens)}  "
            f"over_{MAX_TOKENS}={sum(t > MAX_TOKENS for t in tokens)}  "
            f"with_section={sum(bool(c.headings) for c in chunks) / len(chunks):.0%}  "
            f"with_page={sum(c.page is not None for c in chunks) / len(chunks):.0%}"
        )
        if preview_file:
            for chunk in chunks:
                record = {"ticker": filing["ticker"], "year": path.parent.name, **vars(chunk)}
                preview_file.write(json.dumps(record) + "\n")
    if preview_file:
        preview_file.close()
    print(f"Total: {total_chunks} chunks, {total_tokens} tokens to embed")


async def run_one(filing: dict[str, Any]) -> None:
    client = await create_service_client()
    openai = AsyncOpenAI(api_key=settings.openai_api_key)
    document = await fetch_document(client, filing["accession_number"])
    chunks = chunk_filing(filing_path(filing))
    chunk = next(c for c in chunks if c.page is not None and c.headings)

    await delete_chunks(client, document["id"])
    await insert_chunks(client, openai, document, [chunk])
    print(f"Inserted chunk {chunk.index} (page {chunk.page}, {chunk.token_count} tokens): {chunk.section}")
    verify_chunk(document["id"], chunk)


def verify_chunk(document_id: str, chunk: Chunk) -> None:
    word = max(re.findall(r"[A-Za-z]{4,}", chunk.content), key=len)
    with psycopg.connect(settings.database_url) as conn:
        row = conn.execute(
            "select id, page, section, vector_dims(embedding), embedding::text, "
            "search_vector <> ''::tsvector from document_chunks "
            "where document_id = %s and chunk_index = %s",
            (document_id, chunk.index),
        ).fetchone()
        chunk_id, page, section, dims, embedding, has_search_vector = row
        nearest = conn.execute(
            "select id from document_chunks order by embedding <=> %s::vector limit 1",
            (embedding,),
        ).fetchone()[0]
        full_text_hit = conn.execute(
            "select count(*) from document_chunks "
            "where id = %s and search_vector @@ plainto_tsquery('english', %s)",
            (chunk_id, word),
        ).fetchone()[0]

    checks = {
        f"embedding has {settings.openai_embedding_dimensions} dims": dims == settings.openai_embedding_dimensions,
        "page and section stored": page == chunk.page and section == chunk.section,
        "search_vector generated": has_search_vector,
        "vector search returns the chunk first": nearest == chunk_id,
        f"full-text search finds it ('{word}')": full_text_hit == 1,
    }
    for name, passed in checks.items():
        print(f"  {'PASS' if passed else 'FAIL'}  {name}")
    if not all(checks.values()):
        sys.exit(1)


async def run_all(filings: list[dict[str, Any]]) -> None:
    client = await create_service_client()
    openai = AsyncOpenAI(api_key=settings.openai_api_key)
    for filing in filings:
        document = await fetch_document(client, filing["accession_number"])
        label = f"{document['ticker']} {document['fiscal_year']}"
        if document["metadata"].get("chunk_count") is not None:
            print(f"{label}: skipped (already ingested)")
            continue
        print(f"{label}: chunking...")
        chunks = chunk_filing(filing_path(filing))
        await delete_chunks(client, document["id"])
        await insert_chunks(client, openai, document, chunks)
        metadata = {**document["metadata"], "chunk_count": len(chunks), "chunk_max_tokens": MAX_TOKENS}
        await client.table("source_documents").update({"metadata": metadata}).eq("id", document["id"]).execute()
        print(f"{label}: done, {len(chunks)} chunks")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--dry-run", action="store_true", help="chunk only; no OpenAI calls, no DB writes")
    mode.add_argument("--one", action="store_true", help="embed and insert a single chunk, then verify it")
    parser.add_argument("--ticker")
    parser.add_argument("--year", type=int)
    parser.add_argument("--preview", type=Path, help="dry run: write every chunk to this JSONL file")
    args = parser.parse_args()

    filings = select_filings(args.ticker, args.year)
    if not filings:
        raise SystemExit("No filings match --ticker/--year")
    if args.dry_run:
        dry_run(filings, args.preview)
    elif args.one:
        asyncio.run(run_one(filings[0]))
    else:
        asyncio.run(run_all(filings))


if __name__ == "__main__":
    main()
