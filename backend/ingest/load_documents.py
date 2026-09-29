"""Load the docling Markdown corpus (data/markdown) into source_documents.

Run from backend/: `uv run python -m ingest.load_documents`
Filings already in the table (same accession number) are skipped, not updated.
"""

import asyncio
import json
from pathlib import Path
from typing import Any

from app.config import BACKEND_DIR
from app.database.supabase import create_service_client

MARKDOWN_DIR = BACKEND_DIR.parent / "data" / "markdown"

# The EDGAR manifest carries only tickers; names are fixed for the sample corpus.
COMPANY_NAMES = {
    "AAPL": "Apple Inc.",
    "MSFT": "Microsoft Corporation",
    "NVDA": "NVIDIA Corporation",
    "AMZN": "Amazon.com, Inc.",
    "GOOGL": "Alphabet Inc.",
}


def build_row(filing: dict[str, Any], converter: str) -> dict[str, Any]:
    markdown_path = Path(filing["local_path"])
    return {
        "ticker": filing["ticker"],
        "company_name": COMPANY_NAMES.get(filing["ticker"]),
        "cik": filing["cik"],
        "filing_type": filing["form"],
        "filing_date": filing["filing_date"],
        "report_date": filing["report_date"] or None,
        # Year folder, derived by download.py from report_date (filing_date fallback).
        "fiscal_year": int(markdown_path.parts[0]),
        "accession_number": filing["accession_number"],
        "source_url": filing["source_url"],
        "content_markdown": (MARKDOWN_DIR / markdown_path).read_text(encoding="utf-8"),
        "metadata": {
            "primary_document": filing["primary_document"],
            "markdown_path": filing["local_path"],
            "source_path": filing["source_local_path"],
            "converter": converter,
        },
    }


async def load_documents() -> None:
    manifest = json.loads((MARKDOWN_DIR / "manifest.json").read_text(encoding="utf-8"))
    client = await create_service_client()

    inserted = 0
    for filing in manifest["filings"]:
        row = build_row(filing, manifest["converter"])
        # One filing per request: each body is up to ~1 MB of Markdown.
        response = (
            await client.table("source_documents")
            .upsert(row, on_conflict="accession_number", ignore_duplicates=True)
            .execute()
        )
        status = "inserted" if response.data else "skipped (already loaded)"
        inserted += bool(response.data)
        print(f"{filing['ticker']} {row['fiscal_year']} {filing['accession_number']}: {status}")

    print(f"Inserted {inserted} of {len(manifest['filings'])} filing(s)")


if __name__ == "__main__":
    asyncio.run(load_documents())
