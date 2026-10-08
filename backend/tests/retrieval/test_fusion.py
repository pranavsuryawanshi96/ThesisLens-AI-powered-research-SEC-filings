from uuid import uuid4

import pytest

from app.retrieval.fusion import reciprocal_rank_fusion

A, B, C, D = (uuid4() for _ in range(4))


def ids(fused):
    return [chunk_id for chunk_id, _ in fused]


def test_single_ranking_keeps_its_order():
    assert ids(reciprocal_rank_fusion([[A, B, C]])) == [A, B, C]


def test_chunk_in_both_legs_beats_top_of_one_leg():
    # C is only 3rd in each list, but appearing twice outscores A and D at rank 1 once.
    fused = reciprocal_rank_fusion([[A, B, C], [D, B, C]])

    assert ids(fused)[0] == B
    assert ids(fused).index(C) < ids(fused).index(A)


def test_score_is_sum_of_reciprocal_ranks():
    fused = dict(reciprocal_rank_fusion([[A, B], [B]], k=60))

    assert fused[A] == pytest.approx(1 / 61)
    assert fused[B] == pytest.approx(1 / 62 + 1 / 61)


def test_k_controls_how_much_top_ranks_dominate():
    # With small k, A's single rank-1 hit beats B's two rank-2..3 hits; with k=60 it doesn't.
    rankings = [[A, B], [C, D, B]]

    assert ids(reciprocal_rank_fusion(rankings, k=0))[0] == A
    assert ids(reciprocal_rank_fusion(rankings, k=60))[0] == B


def test_ties_keep_first_seen_order():
    assert ids(reciprocal_rank_fusion([[A], [B]])) == [A, B]
    assert ids(reciprocal_rank_fusion([[B], [A]])) == [B, A]


def test_empty_legs():
    assert reciprocal_rank_fusion([]) == []
    assert reciprocal_rank_fusion([[], []]) == []
    assert ids(reciprocal_rank_fusion([[], [A, B]])) == [A, B]
