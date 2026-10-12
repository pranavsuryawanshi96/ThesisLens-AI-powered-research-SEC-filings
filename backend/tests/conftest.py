from datetime import date
from uuid import uuid4

import pytest

from app.retrieval.types import RetrievedPassage

APPLE_NET_SALES = (
    "| Category | 2024 | Change | 2023 |\n"
    "| iPhone | $ 201,183 | — % | $ 200,583 |\n"
    "| Services | 96,169 | 13 % | 85,200 |\n\n"
    "iPhone net sales were relatively flat during 2024 compared to 2023."
)


@pytest.fixture
def make_passage():
    """Build a RetrievedPassage; defaults to a chunk of Apple's FY2024 net sales table."""

    def make(chunk_index: int = 0, **overrides) -> RetrievedPassage:
        fields = {
            "chunk_id": uuid4(),
            "document_id": uuid4(),
            "chunk_index": chunk_index,
            "content": APPLE_NET_SALES,
            "page": 24,
            "page_end": 24,
            "section": "Item 7 > Segment Operating Performance",
            "ticker": "AAPL",
            "company_name": "Apple Inc.",
            "filing_type": "10-K",
            "filing_date": date(2024, 11, 1),
            "fiscal_year": 2024,
            "accession_number": "0000320193-24-000123",
            "source_url": "https://www.sec.gov/example",
        }
        return RetrievedPassage(**(fields | overrides))

    return make
