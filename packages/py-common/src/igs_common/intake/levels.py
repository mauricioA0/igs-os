"""Competitive level labels coaches write → the 1–10 ``level_score`` the planner matches on.

Deterministic on purpose: the model copies the label it read ("NCAA D3"); this table, not the
model, decides the number. Unknown labels stay unscored.
"""

from __future__ import annotations

import re

# Order matters: the first pattern that matches wins (most specific first).
_LEVELS: tuple[tuple[re.Pattern[str], int], ...] = tuple(
    (re.compile(pattern, re.IGNORECASE), score)
    for pattern, score in (
        (r"\bmls\s*next\b", 8),
        # "DI" alone is a surname particle ("Di Marco"): only with "NCAA" in front.
        (r"\b(d-?1|d-i|div(ision)?\.?\s*(1|i))\b|\bncaa\s+di\b", 8),
        (r"\becnl\b|\bgirls academy\b", 7),
        (r"\b(d-?2|d-?ii|div(ision)?\.?\s*(2|ii))\b", 7),
        (r"\bnaia\b", 6),
        (r"\b(d-?3|d-?iii|div(ision)?\.?\s*(3|iii))\b", 6),
        (r"\b(njcaa|juco|junior college)\b", 5),
        (r"\b(premier|elite)\s+(club|league)\b|\bnpl\b|\bdpl\b", 6),
        (r"\bvarsity\b", 5),
        (r"\b(recreational|rec league|beginner)\b", 2),
    )
)


def level_score(label: str | None) -> int | None:
    if not label:
        return None
    text = label.strip()
    if re.search(r"\bjunior varsity\b|\bjv\b", text, re.IGNORECASE):
        return 4
    for pattern, score in _LEVELS:
        if pattern.search(text):
            return score
    return None
