"""Rank fusion."""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Sequence

RRF_K = 60


def reciprocal_rank_fusion(
    rankings: Sequence[Sequence[str]], rrf_k: int = RRF_K
) -> dict[str, float]:
    """Combine ranked ID lists: each list gives an item `1 / (rrf_k + rank)`.

    Only ranks matter, so scores from different systems (cosine similarity, BM25)
    never need to be put on a common scale. Items found by several lists rise to the top.
    """
    scores: dict[str, float] = defaultdict(float)
    for ranking in rankings:
        for rank, item_id in enumerate(ranking, start=1):
            scores[item_id] += 1.0 / (rrf_k + rank)
    return dict(scores)
