"""Every number the model writes must already be in the facts.

The summary is the only model-written text in the digest. A wrong amount, day count or date
in a morning brief is worse than no brief, so the check is strict: each numeric token in the
text must match some number in the facts (amounts, counts, day offsets, date parts, numbers
inside stored statements). Separators are read both ways (`2,280` / `2.280` = 2280), since the
brief is Spanish and the sources are often English; a separator before exactly three digits
is always a thousands separator.
"""

from __future__ import annotations

import re
from collections.abc import Iterable
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from typing import Any

_NUMBER = re.compile(r"\d+(?:[.,]\d+)*")
_ISO_DATETIME = re.compile(r"^(\d{4}-\d{2}-\d{2})T[\d:.]+(?:Z|[+-]\d{2}:\d{2})?$")
# Identifiers and links carry digits that are not facts (UUIDs, query strings, clock times).
_SKIP_KEYS = frozenset({"id", "link", "generated_at"})


@dataclass(frozen=True)
class NumberCheck:
    ok: bool
    unknown: tuple[str, ...]  # tokens in the text that no fact supports
    checked: int


def allowed_numbers(facts: Any) -> frozenset[Decimal]:
    """All numbers in a JSON-like structure, including those embedded in strings."""
    out: set[Decimal] = set()
    for value in _walk(facts):
        if isinstance(value, bool):
            continue
        if isinstance(value, int | float | Decimal):
            out.add(_norm(Decimal(str(value))))
            out.add(_norm(abs(Decimal(str(value)))))
        elif isinstance(value, str):
            for token in _NUMBER.findall(value):
                out.update(_readings(token))
    return frozenset(out)


def check_numbers(text: str, allowed: Iterable[Decimal]) -> NumberCheck:
    pool = set(allowed)
    tokens = _NUMBER.findall(text)
    unknown = tuple(t for t in tokens if not (_readings(t) & pool))
    return NumberCheck(ok=not unknown, unknown=unknown, checked=len(tokens))


def _walk(value: Any) -> Iterable[Any]:
    if isinstance(value, dict):
        for k, v in value.items():
            if k in _SKIP_KEYS or str(k).endswith("_id"):
                continue
            yield from _walk(v)
    elif isinstance(value, list | tuple | set | frozenset):
        for v in value:
            yield from _walk(v)
    elif isinstance(value, str) and (m := _ISO_DATETIME.match(value)):
        yield m.group(1)  # the day counts, the clock time does not
    else:
        yield value


def _readings(token: str) -> set[Decimal]:
    """Plausible values of a numeric token: grouped integer, and either separator as decimal."""
    readings = {token.replace(",", "").replace(".", "")}
    # One separator with exactly three digits after it groups thousands in both conventions
    # ("3,000" is never 3.0); otherwise it may be a decimal point ("2.5", "2,75").
    if token.count(".") + token.count(",") == 1 and len(re.split(r"[.,]", token)[1]) != 3:
        readings.add(token.replace(",", "."))
    # "2.280,50" / "2,280.50": the last separator is the decimal one.
    for dec, group in ((",", "."), (".", ",")):
        if dec in token and group in token and token.rfind(dec) > token.rfind(group):
            readings.add(token.replace(group, "").replace(dec, "."))
    out = set()
    for r in readings:
        try:
            out.add(_norm(Decimal(r)))
        except InvalidOperation:
            continue
    return out


def _norm(d: Decimal) -> Decimal:
    return d.normalize() if d != 0 else Decimal(0)
