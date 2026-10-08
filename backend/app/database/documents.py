"""Chunk lookups with their filing metadata, shaped for RetrievedPassage."""

from collections import defaultdict
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncConnection

from app.retrieval.types import RetrievedPassage

# Filing metadata comes from source_documents, the source of truth, not the
# denormalized copy in document_chunks.metadata.
PASSAGE_COLUMNS = """
    c.id as chunk_id, c.document_id, c.chunk_index, c.content, c.page,
    (c.metadata->>'page_end')::int as page_end, c.section,
    d.ticker, d.company_name, d.filing_type, d.filing_date, d.fiscal_year,
    d.accession_number, d.source_url
"""


async def get_chunks_by_ids(
    conn: AsyncConnection, chunk_ids: list[UUID]
) -> dict[UUID, RetrievedPassage]:
    """Unordered; callers re-apply their own ranking."""
    if not chunk_ids:
        return {}
    result = await conn.execute(
        text(
            f"select {PASSAGE_COLUMNS} from document_chunks c "
            "join source_documents d on d.id = c.document_id "
            "where c.id = any(:chunk_ids)"
        ),
        {"chunk_ids": chunk_ids},
    )
    passages = [RetrievedPassage.model_validate(dict(row._mapping)) for row in result]
    return {passage.chunk_id: passage for passage in passages}


async def get_surrounding_chunks(
    conn: AsyncConnection, chunk_ids: list[UUID], radius: int
) -> dict[UUID, list[RetrievedPassage]]:
    """For each anchor chunk, the chunks within `radius` of it in the same filing.

    The anchor itself is excluded; each list is ordered by chunk_index.
    """
    if not chunk_ids or radius < 1:
        return {}
    result = await conn.execute(
        text(
            f"select h.id as anchor_id, {PASSAGE_COLUMNS} from document_chunks h "
            "join document_chunks c on c.document_id = h.document_id "
            "and c.chunk_index between h.chunk_index - :radius and h.chunk_index + :radius "
            "and c.id <> h.id "
            "join source_documents d on d.id = c.document_id "
            "where h.id = any(:chunk_ids) "
            "order by h.id, c.chunk_index"
        ),
        {"chunk_ids": chunk_ids, "radius": radius},
    )
    surrounding: dict[UUID, list[RetrievedPassage]] = defaultdict(list)
    for row in result:
        surrounding[row.anchor_id].append(RetrievedPassage.model_validate(dict(row._mapping)))
    return dict(surrounding)
