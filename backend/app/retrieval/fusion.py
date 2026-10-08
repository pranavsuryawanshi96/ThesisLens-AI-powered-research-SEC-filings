"""Reciprocal Rank Fusion: combine ranked lists using rank position only.

Raw scores from pgvector (cosine) and ts_rank_cd are on unrelated scales, so they
are never compared; a chunk earns 1 / (k + rank) from every list it appears in.
"""

from collections import defaultdict
from uuid import UUID


def reciprocal_rank_fusion(rankings: list[list[UUID]], k: int = 60) -> list[tuple[UUID, float]]:
    scores: dict[UUID, float] = defaultdict(float)
    for ranking in rankings:
        for rank, chunk_id in enumerate(ranking, start=1):
            scores[chunk_id] += 1.0 / (k + rank)
    # Stable sort: ties keep first-seen order, so results are deterministic.
    return sorted(scores.items(), key=lambda item: -item[1])
