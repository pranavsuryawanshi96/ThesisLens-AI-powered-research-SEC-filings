import asyncio

from ingest.chunking import Chunk
from ingest.load_chunks import chunk_row, insert_chunks

DOCUMENT = {
    "id": "doc-1",
    "ticker": "AAPL",
    "company_name": "Apple Inc.",
    "filing_type": "10-K",
    "filing_date": "2025-10-31",
    "fiscal_year": 2025,
    "accession_number": "0000320193-25-000079",
    "source_url": "https://www.sec.gov/example.htm",
    "metadata": {},
}


def make_chunk(headings: list[str]) -> Chunk:
    return Chunk(
        index=3,
        content="Net sales by category",
        embed_text="Item 7\nNet sales by category",
        headings=headings,
        page=24,
        page_end=25,
        token_count=9,
    )


def test_chunk_row_maps_columns_and_denormalized_metadata():
    row = chunk_row(DOCUMENT, make_chunk(["Item 7", "Net Sales"]), [0.1, 0.2])

    assert row == {
        "document_id": "doc-1",
        "chunk_index": 3,
        "page": 24,
        "section": "Item 7 > Net Sales",
        "content": "Net sales by category",
        "token_count": 9,
        "embedding": [0.1, 0.2],
        "metadata": {
            "ticker": "AAPL",
            "company_name": "Apple Inc.",
            "filing_type": "10-K",
            "filing_date": "2025-10-31",
            "fiscal_year": 2025,
            "accession_number": "0000320193-25-000079",
            "source_url": "https://www.sec.gov/example.htm",
            "headings": ["Item 7", "Net Sales"],
            "page_end": 25,
        },
    }


def test_chunk_row_without_headings_has_no_section():
    assert chunk_row(DOCUMENT, make_chunk([]), [0.1])["section"] is None


class FakeSupabase:
    def __init__(self):
        self.inserted: list[dict] = []

    def table(self, name):
        assert name == "document_chunks"
        return self

    def insert(self, rows):
        self.inserted.extend(rows)
        return self

    async def execute(self):
        return None


def test_insert_chunks_without_openai_stores_null_embeddings():
    client = FakeSupabase()

    asyncio.run(insert_chunks(client, None, DOCUMENT, [make_chunk(["Item 7"])]))

    [row] = client.inserted
    assert row["embedding"] is None
    assert row["content"] == "Net sales by category"
