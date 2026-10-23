"""Relative demo dates: fixtures are written as of FIXTURE_ANCHOR and replayed relative to today.

The demo story ("enrollment fees overdue a week ago, hotel releases the blocks in 9 days, the
proposal approval expires in 2 days") must read the same whenever the demo is reset. Seeding
shifts every date in the sales and accounts fixtures by ``anchor - FIXTURE_ANCHOR`` days:

* structured values — ``date``/``datetime`` objects and ISO strings ("2026-10-31",
  "2026-10-22T07:40:00-03:00");
* dates written inside text — "October 15", "Oct 31st", "March 6–15, 2027", "15/10",
  "6–15/3/2027", "6–15 mar 2027", "15 de octubre", "June 2027", "the March blocks", "marzo" —
  re-rendered in the same style. A day/month without a year resolves to the occurrence nearest
  FIXTURE_ANCHOR (so "March" in an October fixture is next March).

``DEMO_ANCHOR`` (YYYY-MM-DD) pins the anchor; default is today in Buenos Aires. Tests pin it to
FIXTURE_ANCHOR so their expectations stay literal.
"""

from __future__ import annotations

import os
import re
from collections.abc import Callable
from datetime import date, datetime, timedelta
from typing import Any
from zoneinfo import ZoneInfo

FIXTURE_ANCHOR = date(2026, 10, 22)
OPS_TZ = ZoneInfo("America/Argentina/Buenos_Aires")

_EN_FULL = [
    "January", "February", "March", "April", "May", "June",
    "July", "August", "September", "October", "November", "December",
]  # fmt: skip
_EN_ABBR = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]
_ES_FULL = [
    "enero", "febrero", "marzo", "abril", "mayo", "junio",
    "julio", "agosto", "septiembre", "octubre", "noviembre", "diciembre",
]  # fmt: skip
_ES_ABBR = ["ene", "feb", "mar", "abr", "may", "jun", "jul", "ago", "sep", "oct", "nov", "dic"]


def demo_anchor() -> date:
    raw = os.environ.get("DEMO_ANCHOR")
    if raw:
        return date.fromisoformat(raw)
    return datetime.now(OPS_TZ).date()


def shift_days(anchor: date | None = None) -> int:
    return ((anchor or demo_anchor()) - FIXTURE_ANCHOR).days


# ── Structured values ──────────────────────────────────────────────────────

_ISO_DATE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
_ISO_DT = re.compile(r"^\d{4}-\d{2}-\d{2}[T ]\d{2}:\d{2}")


def shift_tree(obj: Any, days: int, *, texts: bool = True) -> Any:
    """Return a copy of ``obj`` with every date (and, if ``texts``, every date in prose) shifted."""
    if days == 0:
        return obj
    if isinstance(obj, dict):
        return {k: shift_tree(v, days, texts=texts) for k, v in obj.items()}
    if isinstance(obj, list):
        return [shift_tree(v, days, texts=texts) for v in obj]
    if isinstance(obj, datetime | date):
        return obj + timedelta(days=days)
    if isinstance(obj, str):
        if _ISO_DATE.match(obj):
            return (date.fromisoformat(obj) + timedelta(days=days)).isoformat()
        if _ISO_DT.match(obj):
            return (datetime.fromisoformat(obj) + timedelta(days=days)).isoformat()
        return shift_text(obj, days) if texts else obj
    return obj


# ── Dates inside text ──────────────────────────────────────────────────────


def _nearest(month: int, day: int) -> date:
    """The occurrence of month/day nearest FIXTURE_ANCHOR (fixtures omit obvious years)."""
    best: date | None = None
    for year in (FIXTURE_ANCHOR.year - 1, FIXTURE_ANCHOR.year, FIXTURE_ANCHOR.year + 1):
        try:
            candidate = date(year, month, day)
        except ValueError:
            continue
        if best is None or abs((candidate - FIXTURE_ANCHOR).days) < abs(
            (best - FIXTURE_ANCHOR).days
        ):
            best = candidate
    assert best is not None
    return best


def _resolve(month: int, day: int, year: str | None) -> date:
    return date(int(year), month, day) if year else _nearest(month, day)


def _ordinal(day: int) -> str:
    if 11 <= day % 100 <= 13:
        return "th"
    return {1: "st", 2: "nd", 3: "rd"}.get(day % 10, "th")


def _en_month(m: str) -> tuple[int, list[str]] | None:
    key = m.rstrip(".")
    for names in (_EN_FULL, _EN_ABBR):
        if key in names:
            return names.index(key) + 1, names
    if key == "Sept":
        return 9, _EN_ABBR
    return None


def _es_month(m: str) -> tuple[int, list[str]] | None:
    key = m.lower().rstrip(".")
    for names in (_ES_FULL, _ES_ABBR):
        if key in names:
            return names.index(key) + 1, names
    if key == "setiembre":
        return 9, _ES_FULL
    return None


_EN = r"(?:January|February|March|April|May|June|July|August|September|October|November|December|Jan|Feb|Mar|Apr|Jun|Jul|Aug|Sept|Sep|Oct|Nov|Dec)\.?"  # noqa: E501
_ES = r"(?:enero|febrero|marzo|abril|mayo|junio|julio|agosto|septiembre|setiembre|octubre|noviembre|diciembre|ene|feb|mar|abr|may|jun|jul|ago|sep|oct|nov|dic)\.?"  # noqa: E501
_DASH = r"[–-]"

# "March 6–15, 2027" · "October 31st" · "Oct 28"
_EN_DAY = re.compile(
    rf"\b(?P<m>{_EN}) (?P<d1>\d{{1,2}})(?P<suf>st|nd|rd|th)?"
    rf"(?:{_DASH}(?P<d2>\d{{1,2}}))?(?:, (?P<y>\d{{4}}))?\b"
)
# "6–15/3/2027" · "15/10" (only after el/del/al/antes del/"("/", " — never "24/7" or "9/10")
_DM = re.compile(
    r"(?P<pre>(?:\b(?:el|del|al)\s)|\(|, )(?P<d1>\d{1,2})(?:[–-](?P<d2>\d{1,2}))?"
    r"/(?P<m>\d{1,2})(?:/(?P<y>\d{4}))?(?![\d/])"
)
_DM_RANGE_Y = re.compile(r"\b(?P<d1>\d{1,2})[–-](?P<d2>\d{1,2})/(?P<m>\d{1,2})/(?P<y>\d{4})\b")
# "6–15 mar 2027" · "15 de octubre" · "15 de octubre de 2026"
_ES_DAY = re.compile(
    rf"\b(?P<d1>\d{{1,2}})(?:{_DASH}(?P<d2>\d{{1,2}}))?(?P<de> de)? (?P<m>{_ES})"
    rf"(?:(?P<yde> de)? (?P<y>\d{{4}}))?\b"
)
# "June 2027" · "marzo de 2027" (month + year, no day)
_EN_MY = re.compile(rf"\b(?P<m>{_EN}) (?P<y>\d{{4}})\b")
_ES_MY = re.compile(rf"\b(?P<m>{_ES})(?P<de> de)? (?P<y>\d{{4}})\b")
# Bare month names: English capitalized (not "May", the verb), Spanish full names.
_EN_BARE = re.compile(
    r"\b(?P<m>January|February|March|April|June|July|August|September|October|November|December)\b"
)
_ES_BARE = re.compile(
    r"\b(?P<m>enero|febrero|marzo|abril|junio|julio|agosto|septiembre|setiembre|octubre|noviembre|diciembre)\b"  # noqa: E501
)

_PLACEHOLDER = "\x00{}\x00"


def shift_text(text: str, days: int) -> str:
    if days == 0 or not text:
        return text
    shift = timedelta(days=days)
    done: list[str] = []

    def keep(rendered: str) -> str:
        done.append(rendered)
        return _PLACEHOLDER.format(len(done) - 1)

    def sub(pattern: re.Pattern[str], fn: Callable[[re.Match[str]], str | None]) -> None:
        nonlocal text

        def repl(m: re.Match[str]) -> str:
            out = fn(m)
            return m.group(0) if out is None else keep(out)

        text = pattern.sub(repl, text)

    def en_day(m: re.Match[str]) -> str | None:
        info = _en_month(m["m"])
        if info is None:
            return None
        month, names = info
        dot = "." if m["m"].endswith(".") else ""
        start = _resolve(month, int(m["d1"]), m["y"]) + shift
        name = lambda d: names[d.month - 1] + dot  # noqa: E731
        suf = _ordinal(start.day) if m["suf"] else ""
        year = f", {start.year}" if m["y"] else ""
        if not m["d2"]:
            return f"{name(start)} {start.day}{suf}{year}"
        end = _resolve(month, int(m["d2"]), m["y"]) + shift
        if end.month == start.month:
            return f"{name(start)} {start.day}–{end.day}{year}"
        return f"{name(start)} {start.day}–{name(end)} {end.day}{year}"

    def dm_range_y(m: re.Match[str]) -> str:
        month, year = int(m["m"]), m["y"]
        start = _resolve(month, int(m["d1"]), year) + shift
        end = _resolve(month, int(m["d2"]), year) + shift
        if start.month == end.month:
            return f"{start.day}–{end.day}/{start.month}/{start.year}"
        return f"{start.day}/{start.month}–{end.day}/{end.month}/{end.year}"

    def dm(m: re.Match[str]) -> str | None:
        month = int(m["m"])
        if not 1 <= month <= 12 or int(m["d1"]) > 31:
            return None
        start = _resolve(month, int(m["d1"]), m["y"]) + shift
        year = f"/{start.year}" if m["y"] else ""
        if m["d2"]:
            end = _resolve(month, int(m["d2"]), m["y"]) + shift
            body = (
                f"{start.day}–{end.day}/{start.month}"
                if start.month == end.month
                else f"{start.day}/{start.month}–{end.day}/{end.month}"
            )
        else:
            body = f"{start.day}/{start.month}"
        return f"{m['pre']}{body}{year}"

    def es_day(m: re.Match[str]) -> str | None:
        info = _es_month(m["m"])
        if info is None:
            return None
        month, names = info
        dot = "." if m["m"].endswith(".") else ""
        de = m["de"] or ""
        start = _resolve(month, int(m["d1"]), m["y"]) + shift
        year = f"{m['yde'] or ''} {start.year}" if m["y"] else ""
        if not m["d2"]:
            return f"{start.day}{de} {names[start.month - 1]}{dot}{year}"
        end = _resolve(month, int(m["d2"]), m["y"]) + shift
        if start.month == end.month:
            return f"{start.day}–{end.day}{de} {names[start.month - 1]}{dot}{year}"
        return (
            f"{start.day}{de} {names[start.month - 1]}{dot}–{end.day}{de} "
            f"{names[end.month - 1]}{dot}{year}"
        )

    def month_year(parse: Callable[[str], tuple[int, list[str]] | None]):  # noqa: ANN202
        def fn(m: re.Match[str]) -> str | None:
            info = parse(m["m"])
            if info is None:
                return None
            month, names = info
            dot = "." if m["m"].endswith(".") else ""
            mid = date(int(m["y"]), month, 15) + shift
            de = m.groupdict().get("de") or ""
            return f"{names[mid.month - 1]}{dot}{de} {mid.year}"

        return fn

    def bare(parse: Callable[[str], tuple[int, list[str]] | None]):  # noqa: ANN202
        def fn(m: re.Match[str]) -> str | None:
            info = parse(m["m"])
            if info is None:
                return None
            month, names = info
            mid = _nearest(month, 15) + shift
            return names[mid.month - 1]

        return fn

    sub(_EN_DAY, en_day)
    sub(_DM_RANGE_Y, dm_range_y)
    sub(_DM, dm)
    sub(_ES_DAY, es_day)
    sub(_EN_MY, month_year(_en_month))
    sub(_ES_MY, month_year(_es_month))
    sub(_EN_BARE, bare(_en_month))
    sub(_ES_BARE, bare(_es_month))
    for i, rendered in enumerate(done):
        text = text.replace(_PLACEHOLDER.format(i), rendered)
    return text
