"""Ranking metrics with binary relevance. All return values in [0, 1]."""

from __future__ import annotations

import math
from collections.abc import Iterable, Sequence
from statistics import fmean


def recall_at_k(ranked: Sequence[str], relevant: Iterable[str], k: int) -> float:
    rel = set(relevant)
    if not rel:
        return 0.0
    return len(rel.intersection(ranked[:k])) / len(rel)


def hit_at_k(ranked: Sequence[str], relevant: Iterable[str], k: int) -> float:
    rel = set(relevant)
    return 1.0 if rel.intersection(ranked[:k]) else 0.0


def reciprocal_rank(ranked: Sequence[str], relevant: Iterable[str]) -> float:
    rel = set(relevant)
    for i, doc_id in enumerate(ranked, start=1):
        if doc_id in rel:
            return 1.0 / i
    return 0.0


def ndcg_at_k(ranked: Sequence[str], relevant: Iterable[str], k: int) -> float:
    rel = set(relevant)
    if not rel:
        return 0.0
    dcg = sum(1.0 / math.log2(i + 1) for i, d in enumerate(ranked[:k], start=1) if d in rel)
    ideal = sum(1.0 / math.log2(i + 1) for i in range(1, min(len(rel), k) + 1))
    return dcg / ideal


def summarize(per_query: Sequence[dict[str, float]]) -> dict[str, float]:
    """Mean of every metric across queries (keys taken from the first row)."""
    if not per_query:
        return {}
    return {key: round(fmean(row[key] for row in per_query), 4) for key in per_query[0]}
