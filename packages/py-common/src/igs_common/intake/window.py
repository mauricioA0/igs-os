"""The form's free-text "Target Travel Window" → a date range, for scoring and sorting only.

"Summer 2026", "Spring break 2027", "March 2027", "Fall '27", "2027". A window is never turned
into a lead's ``travel_start``: "Spring break" is a range, not a day.
"""

from __future__ import annotations

import re
from calendar import monthrange
from datetime import date

_SEASONS = {
    # (start month, start day, end month, end day, end is next year)
    "spring break": (3, 1, 4, 15, False),
    "winter break": (12, 15, 1, 15, True),
    "christmas break": (12, 15, 1, 15, True),
    "summer": (6, 1, 8, 31, False),
    "spring": (3, 1, 5, 31, False),
    "fall": (9, 1, 11, 30, False),
    "autumn": (9, 1, 11, 30, False),
    "winter": (12, 1, 2, 28, True),
    "preseason": (7, 15, 8, 20, False),
}
_MONTHS = "jan feb mar apr may jun jul aug sep oct nov dec".split()
_YEAR = re.compile(r"\b(20\d{2})\b|'(\d{2})\b")


def parse_window(text: str) -> tuple[date, date] | None:
    if not text:
        return None
    lowered = text.lower()
    year_match = _YEAR.search(lowered)
    if year_match is None:
        return None
    full, short = year_match.groups()
    year = int(full) if full else 2000 + int(short)
    for name, (sm, sd, em, ed, wraps) in _SEASONS.items():
        if name in lowered:
            return date(year, sm, sd), date(year + 1 if wraps else year, em, ed)
    for i, abbr in enumerate(_MONTHS, start=1):
        if re.search(rf"\b{abbr}[a-z]*\.?\b", lowered):
            return date(year, i, 1), date(year, i, monthrange(year, i)[1])
    return date(year, 1, 1), date(year, 12, 31)
