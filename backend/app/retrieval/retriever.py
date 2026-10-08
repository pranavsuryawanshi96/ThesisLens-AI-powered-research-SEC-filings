"""Query → fused, ranked source passages with surrounding context.

Pipeline (same shape as the ai-cookbook hybrid-retrieval tutorial): fetch
`candidate_k` from the semantic and the full-text leg, fuse with RRF, keep `top_k`,
then hydrate those chunks with filing metadata and neighboring chunks.
"""

import asyncio
from uuid import UUID

from openai import AsyncOpenAI
from sqlalchemy.ext.asyncio import AsyncEngine

from app.config import settings
from app.database import documents
from app.retrieval import queries
from app.retrieval.embeddings import embed_query
from app.retrieval.fusion import reciprocal_rank_fusion
from app.retrieval.types import RankedChunkHit, RetrievedPassage, SearchFilters


class DocumentRetriever:
    def __init__(self, engine: AsyncEngine, openai: AsyncOpenAI):
        self.engine = engine
        self.openai = openai

    async def search(
        self,
        query: str,
        filters: SearchFilters | None = None,
        *,
        top_k: int | None = None,
        neighbor_radius: int | None = None,
    ) -> list[RetrievedPassage]:
        top_k = settings.retrieval_top_k if top_k is None else top_k
        radius = settings.retrieval_neighbor_radius if neighbor_radius is None else neighbor_radius

        semantic, lexical = await self.search_legs(query, filters)
        fused = reciprocal_rank_fusion(
            [[hit.chunk_id for hit in semantic], [hit.chunk_id for hit in lexical]],
            k=settings.retrieval_rrf_k,
        )[:top_k]
        chunk_ids = [chunk_id for chunk_id, _ in fused]

        async with self.engine.connect() as conn:
            by_id = await documents.get_chunks_by_ids(conn, chunk_ids)
            surrounding = await documents.get_surrounding_chunks(conn, chunk_ids, radius)

        semantic_ranks = {hit.chunk_id: hit.rank for hit in semantic}
        lexical_ranks = {hit.chunk_id: hit.rank for hit in lexical}
        # A neighbor that is itself a hit, or already attached to a higher-ranked hit,
        # is not repeated: the agent should see each chunk once.
        claimed = set(chunk_ids)
        passages: list[RetrievedPassage] = []
        for chunk_id, score in fused:
            # Absent only if ingestion rebuilt the filing between the two queries.
            if chunk_id not in by_id:
                continue
            neighbors = [n for n in surrounding.get(chunk_id, []) if n.chunk_id not in claimed]
            claimed.update(n.chunk_id for n in neighbors)
            passages.append(
                by_id[chunk_id].model_copy(
                    update={
                        "fusion_score": score,
                        "semantic_rank": semantic_ranks.get(chunk_id),
                        "lexical_rank": lexical_ranks.get(chunk_id),
                        "neighbors": neighbors,
                    }
                )
            )
        return passages

    async def search_legs(
        self, query: str, filters: SearchFilters | None, candidate_k: int | None = None
    ) -> tuple[list[RankedChunkHit], list[RankedChunkHit]]:
        """Both ranked legs before fusion; public so the eval can score each leg alone."""
        limit = settings.retrieval_candidate_k if candidate_k is None else candidate_k

        async def semantic() -> list[RankedChunkHit]:
            vector = await embed_query(self.openai, query)
            async with self.engine.connect() as conn:
                return await queries.semantic_search(conn, vector, filters, limit)

        async def lexical() -> list[RankedChunkHit]:
            # Separate connection: one connection cannot run two queries at once.
            async with self.engine.connect() as conn:
                return await queries.full_text_search(conn, query, filters, limit)

        return await asyncio.gather(semantic(), lexical())

    async def read_chunk(self, chunk_id: UUID) -> RetrievedPassage | None:
        async with self.engine.connect() as conn:
            return (await documents.get_chunks_by_ids(conn, [chunk_id])).get(chunk_id)

    async def read_surrounding_chunks(
        self, chunk_id: UUID, radius: int | None = None
    ) -> list[RetrievedPassage]:
        """The chunk and its neighbors, in filing order."""
        radius = settings.retrieval_neighbor_radius if radius is None else radius
        async with self.engine.connect() as conn:
            anchor = (await documents.get_chunks_by_ids(conn, [chunk_id])).get(chunk_id)
            if anchor is None:
                return []
            surrounding = await documents.get_surrounding_chunks(conn, [chunk_id], radius)
        return sorted([anchor, *surrounding.get(chunk_id, [])], key=lambda p: p.chunk_index)


def format_passages_for_agent(passages: list[RetrievedPassage]) -> str:
    """Bounded plain text for the LLM: each chunk is headed by the id it must cite."""
    if not passages:
        return "No matching passages found."
    blocks = []
    for number, passage in enumerate(passages, start=1):
        window = sorted([passage, *passage.neighbors], key=lambda p: p.chunk_index)
        chunks = [format_chunk(p, is_match=p.chunk_id == passage.chunk_id) for p in window]
        blocks.append(f"## Result {number}\n\n" + "\n\n".join(chunks))
    return "\n\n---\n\n".join(blocks)


def format_chunk(passage: RetrievedPassage, *, is_match: bool = True) -> str:
    role = "match" if is_match else "context"
    section = f" · {passage.section}" if passage.section else ""
    return f"[chunk:{passage.chunk_id}] {passage.label}{section} ({role})\n{passage.content}"
