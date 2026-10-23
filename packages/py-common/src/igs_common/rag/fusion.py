"""Reciprocal Rank Fusion, the same formula the Agent Retrieval service applies server-side."""

from __future__ import annotations

from collections.abc import Sequence

RRF_K = 60


def rrf(
    rankings: Sequence[Sequence[str]],
    *,
    weights: Sequence[float] | None = None,
    k: int = RRF_K,
) -> list[tuple[str, float]]:
    """Fuse ranked id lists → [(id, score)] best first; ties broken by first appearance."""
    if weights is not None and len(weights) != len(rankings):
        raise ValueError("one weight per ranking")
    scores: dict[str, float] = {}
    first_seen: dict[str, int] = {}
    order = 0
    for i, ranking in enumerate(rankings):
        w = 1.0 if weights is None else weights[i]
        for rank, item in enumerate(ranking, start=1):
            scores[item] = scores.get(item, 0.0) + w / (k + rank)
            if item not in first_seen:
                first_seen[item] = order
                order += 1
    return sorted(scores.items(), key=lambda kv: (-kv[1], first_seen[kv[0]]))
