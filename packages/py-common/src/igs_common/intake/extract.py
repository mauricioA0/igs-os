"""Inquiry text → the fields a lead needs. Unknown stays null; nothing is invented.

Two extractors produce the same ``Extraction``:

- ``extract_with_llm``: the extractor model reads the inquiry and, for every value it fills,
  copies the exact words that support it. A value whose quote is not a verbatim span of what the
  coach wrote is dropped (``rejected``), so a guessed sport or a made-up group size never reaches
  a lead.
- ``extract_with_rules``: regular expressions over the same text. Runs when no model is
  configured or the model fails, so intake never stops; it finds less, never more.

Either way, derived values come from code, not from the model: ``level_score`` from the level
label (``levels.py``), ``travel_start`` only from an explicit date or month.
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass, field
from datetime import date
from typing import Any, Literal

from pydantic import BaseModel, Field, ValidationError

from igs_common.llm import GenerateOptions, LLMClient, LLMError, Message, Role

from .levels import level_score

Sport = Literal["soccer", "rugby", "field_hockey", "volleyball", "basketball"]
Gender = Literal["men", "women", "mixed"]
Destination = Literal["Argentina", "Brazil", "Costa Rica", "Spain"]

# What the leads table requires (``igs_common.db.models.Lead``): the intake becomes a lead only
# once all of these are known.
LEAD_REQUIRED = (
    "sport",
    "gender",
    "age_group",
    "level_score",
    "group_size",
    "destination_country",
    "travel_start",
    "duration_days",
)


class Evidence(BaseModel):
    field: str = Field(description="Name of the field this quote supports.")
    quote: str = Field(description="Exact words copied from the inquiry, 2–20 words.")


class ExtractionOutput(BaseModel):
    """What the model returns. Every non-null value needs an `evidence` entry."""

    sport: Sport | None
    gender: Gender | None
    age_group: str | None = Field(description='As written: "U17", "college", "varsity", …')
    level_label: str | None = Field(description='Competitive level as written: "NCAA D3", "ECNL"')
    group_size: int | None = Field(description="Travelers (players + staff) if a number is stated")
    destination_country: Destination | None
    travel_date: date | None = Field(description="Only if an exact first travel day is written")
    travel_month: str | None = Field(description='Only if a month and year are written: "2027-03"')
    duration_days: int | None = Field(description="Only if a number of days/nights is stated")
    budget_per_person_usd: int | None = Field(description="Only if a per-person amount is stated")
    goals: str | None = Field(description="What they want from the tour, in their words")
    evidence: list[Evidence]


@dataclass(frozen=True)
class Extraction:
    values: dict[str, Any]
    evidence: dict[str, str]
    rejected: dict[str, str] = field(default_factory=dict)
    method: Literal["llm", "rules"] = "rules"
    model: str | None = None

    @property
    def missing(self) -> list[str]:
        return [name for name in LEAD_REQUIRED if self.values.get(name) is None]

    def merged_over(self, older: dict[str, Any]) -> dict[str, Any]:
        """A follow-up message fills gaps; it never erases what the coach already told us."""
        return {**older, **{k: v for k, v in self.values.items() if v is not None}}

    def to_json(self) -> dict[str, Any]:
        return {
            "values": {
                k: (v.isoformat() if isinstance(v, date) else v) for k, v in self.values.items()
            },
            "evidence": self.evidence,
            "rejected": self.rejected,
            "method": self.method,
        }


INSTRUCTIONS = """\
You read one inquiry sent to Infinity Global Sports, a company that runs international sports
tours for US college, club and school teams. Fill the fields ONLY with what the inquiry states.

Rules:
- If something is not stated, return null. Do not guess from the program name, the season or
  what is typical. "Spring break 2027" is not a date and not a month: leave travel_date and
  travel_month null.
- sport: only if the inquiry names it (or the program name contains it, e.g. "Women's Soccer").
- gender: men / women / mixed, only if stated ("women's", "girls", "boys", "co-ed").
- destination_country: only Argentina, Brazil, Costa Rica or Spain, and only if named (a city in
  that country counts: Buenos Aires → Argentina, Rio → Brazil).
- group_size: the number of travelers if a number is stated; "around 25" → 25.
- budget_per_person_usd: only a per-person figure in dollars.
- For every non-null field, add an evidence entry whose quote is copied character for character
  from the inquiry. A value without an exact quote will be discarded.
"""


async def extract_with_llm(llm: LLMClient, source: str) -> Extraction:
    result = await llm.generate(
        Role.EXTRACTOR,
        [Message("user", f"<inquiry>\n{source}\n</inquiry>")],
        output_model=ExtractionOutput,
        options=GenerateOptions(
            instructions=INSTRUCTIONS,
            reasoning_effort="low",
            metadata={"feature": "intake.extract"},
            cache_key="intake-extract",
        ),
    )
    if result.parsed is None:
        raise LLMError(f"intake extraction returned no structured output ({result.finish_reason})")
    out = result.parsed
    quotes: dict[str, str] = {}
    for item in out.evidence:
        quotes.setdefault(item.field, item.quote)
    raw: dict[str, Any] = {
        "sport": out.sport,
        "gender": out.gender,
        "age_group": out.age_group,
        "level_label": out.level_label,
        "group_size": out.group_size,
        "destination_country": out.destination_country,
        "travel_date": out.travel_date,
        "travel_month": out.travel_month,
        "duration_days": out.duration_days,
        "budget_per_person_usd": out.budget_per_person_usd,
        "goals": out.goals,
    }
    kept: dict[str, Any] = {}
    evidence: dict[str, str] = {}
    rejected: dict[str, str] = {}
    normalized_source = _normalize(source)
    for name, value in raw.items():
        if value is None:
            continue
        quote = quotes.get(name, "")
        if not quote.strip():
            rejected[name] = "no evidence quote"
        elif _normalize(quote) not in normalized_source:
            rejected[name] = "evidence is not a verbatim span of the inquiry"
        else:
            kept[name] = value
            evidence[name] = quote.strip()
    return _finish(kept, evidence, rejected, method="llm", model=result.model)


# ── Rules ─────────────────────────────────────────────────────────────────────

_SPORTS: tuple[tuple[str, Sport], ...] = (
    (r"field\s*hockey", "field_hockey"),
    (r"soccer|f[úu]tbol\b|football club|\bfc\b", "soccer"),
    (r"rugby", "rugby"),
    (r"volleyball", "volleyball"),
    (r"basketball", "basketball"),
)
_GENDERS: tuple[tuple[str, Gender], ...] = (
    (r"\bco-?ed\b|\bmixed\b", "mixed"),
    (r"\bwomen'?s\b|\bgirls'?\b|\bwomen\b|\bfemale\b", "women"),
    (r"\bmen'?s\b|\bboys'?\b|\bmale\b", "men"),
)
_DESTINATIONS: tuple[tuple[str, Destination], ...] = (
    (r"argentina|buenos aires|c[óo]rdoba|rosario|mendoza", "Argentina"),
    (r"brazil|brasil|rio de janeiro|\brio\b|s[ãa]o paulo", "Brazil"),
    (r"costa rica|san jos[ée]", "Costa Rica"),
    (r"\bspain\b|espa[ñn]a|madrid|barcelona|valencia", "Spain"),
)
_LEVEL = re.compile(
    r"\b(NCAA\s+(?:D(?:-?[123]|I{1,3})|Division\s+(?:I{1,3}|[123]))|D-?[123]\b|D(?:II|III)\b|"
    r"Division\s+(?:I{1,3}|[123])\b|NAIA|NJCAA|JUCO|ECNL(?:\s+RL)?|MLS\s+Next|Girls\s+Academy|"
    r"(?:junior\s+)?varsity|JV|NPL|DPL)\b",
    re.IGNORECASE,
)
_AGE = re.compile(
    r"\b(U-?\d{2}|under[- ]\d{2}|\d{2}U|high school|college|collegiate|university|middle school)\b",
    re.IGNORECASE,
)
_GROUP = re.compile(
    r"\b(?:about|around|roughly|approximately|~)?\s*(\d{1,3})\s*(?:-|to)?\s*(?:\d{1,3}\s*)?"
    r"(players|athletes|travel+ers|people|girls|boys|kids|student[- ]athletes|participants|"
    r"people in total|including staff)\b",
    re.IGNORECASE,
)
_DURATION = re.compile(r"\b(\d{1,2})\s*(?:-\s*)?(days?|nights?)\b", re.IGNORECASE)
_BUDGET = re.compile(
    r"(?:US)?\$\s?(\d{1,2}(?:,\d{3}|\d{3})|\d{3,5})\s*(?:usd\s*)?"
    r"(?:per\s+(?:person|player|athlete|traveler|traveller)|/\s*(?:person|player|pp)|pp|each)\b",
    re.IGNORECASE,
)
_MONTHS = {
    m: i
    for i, names in enumerate(
        (
            ("january", "jan"),
            ("february", "feb"),
            ("march", "mar"),
            ("april", "apr"),
            ("may",),
            ("june", "jun"),
            ("july", "jul"),
            ("august", "aug"),
            ("september", "sep", "sept"),
            ("october", "oct"),
            ("november", "nov"),
            ("december", "dec"),
        ),
        start=1,
    )
    for m in names
}
_MONTH_NAMES = "|".join(sorted(_MONTHS, key=len, reverse=True))
_EXACT_DATE = re.compile(
    rf"\b({_MONTH_NAMES})\.?\s+(\d{{1,2}})(?:st|nd|rd|th)?(?:\s*[-–]\s*\d{{1,2}})?,?\s+(20\d{{2}})\b",
    re.IGNORECASE,
)
_ISO_DATE = re.compile(r"\b(20\d{2})-(\d{2})-(\d{2})\b")
_MONTH_YEAR = re.compile(rf"\b({_MONTH_NAMES})\.?\s+(20\d{{2}})\b", re.IGNORECASE)


def extract_with_rules(source: str) -> Extraction:
    values: dict[str, Any] = {}
    evidence: dict[str, str] = {}

    def first(name: str, options: tuple[tuple[str, Any], ...]) -> None:
        for pattern, value in options:
            match = re.search(pattern, source, re.IGNORECASE)
            if match:
                values[name], evidence[name] = value, match.group(0)
                return

    first("sport", _SPORTS)
    first("gender", _GENDERS)
    first("destination_country", _DESTINATIONS)
    if match := _LEVEL.search(source):
        values["level_label"], evidence["level_label"] = match.group(1), match.group(0)
    if match := _AGE.search(source):
        values["age_group"], evidence["age_group"] = match.group(1), match.group(0)
    if match := _GROUP.search(source):
        size = int(match.group(1))
        if 4 <= size <= 120:
            values["group_size"], evidence["group_size"] = size, match.group(0).strip()
    if match := _DURATION.search(source):
        days = int(match.group(1)) + (1 if match.group(2).lower().startswith("night") else 0)
        if 3 <= days <= 30:
            values["duration_days"], evidence["duration_days"] = days, match.group(0)
    if match := _BUDGET.search(source):
        values["budget_per_person_usd"] = int(match.group(1).replace(",", ""))
        evidence["budget_per_person_usd"] = match.group(0)
    if match := _ISO_DATE.search(source):
        try:
            values["travel_date"] = date(int(match[1]), int(match[2]), int(match[3]))
            evidence["travel_date"] = match.group(0)
        except ValueError:
            pass
    elif match := _EXACT_DATE.search(source):
        try:
            values["travel_date"] = date(int(match[3]), _MONTHS[match[1].lower()], int(match[2]))
            evidence["travel_date"] = match.group(0)
        except ValueError:
            pass
    if "travel_date" not in values and (match := _MONTH_YEAR.search(source)):
        values["travel_month"] = f"{match[2]}-{_MONTHS[match[1].lower()]:02d}"
        evidence["travel_month"] = match.group(0)
    return _finish(values, evidence, {}, method="rules", model=None)


async def extract(llm: LLMClient | None, source: str) -> Extraction:
    """The model when there is one; the rules when there isn't or it fails."""
    if llm is not None:
        try:
            return await extract_with_llm(llm, source)
        except (LLMError, ValidationError):
            pass  # an outage or a malformed answer must not lose the inquiry
    return extract_with_rules(source)


# ── Shared ────────────────────────────────────────────────────────────────────


def _finish(
    values: dict[str, Any],
    evidence: dict[str, str],
    rejected: dict[str, str],
    *,
    method: Literal["llm", "rules"],
    model: str | None,
) -> Extraction:
    out: dict[str, Any] = {name: None for name in (*LEAD_REQUIRED, "budget_per_person_usd")}
    out.update(values)
    age = out.get("age_group")
    if isinstance(age, str) and _COLLEGE.fullmatch(age.strip()):
        out["age_group"] = "College"
    elif age is None and _COLLEGE_LEVEL.search(values.get("level_label") or ""):
        # NCAA / NAIA / NJCAA only exist in college: the level names the age group.
        out["age_group"] = "College"
        if "level_label" in evidence:
            evidence["age_group"] = evidence["level_label"]
    out["level_score"] = level_score(values.get("level_label"))
    out["travel_start"], out["travel_start_precision"] = _travel_start(values)
    for name in ("group_size", "duration_days", "budget_per_person_usd"):
        if out.get(name) is not None and out[name] <= 0:
            rejected[name] = "not a positive number"
            out[name] = None
    return Extraction(values=out, evidence=evidence, rejected=rejected, method=method, model=model)


def _travel_start(values: dict[str, Any]) -> tuple[date | None, str | None]:
    """An exact day, or the 1st of a stated month (flagged); seasons give nothing."""
    exact = values.get("travel_date")
    if isinstance(exact, date):
        return exact, "day"
    month = values.get("travel_month")
    if isinstance(month, str) and (m := re.fullmatch(r"(20\d{2})-(\d{2})", month.strip())):
        if 1 <= int(m[2]) <= 12:
            return date(int(m[1]), int(m[2]), 1), "month"
    return None, None


_COLLEGE = re.compile(r"college|collegiate|university", re.IGNORECASE)
_COLLEGE_LEVEL = re.compile(
    r"\b(ncaa|naia|njcaa|juco|d-?[123]|d-?i{1,3}|division\s+(i{1,3}|[123]))\b", re.IGNORECASE
)

_QUOTES = str.maketrans({"‘": "'", "’": "'", "“": '"', "”": '"', "–": "-", "—": "-"})
_SPACE = re.compile(r"\s+")


def _normalize(text: str) -> str:
    text = unicodedata.normalize("NFKC", text).translate(_QUOTES)
    return _SPACE.sub(" ", text).strip().casefold()
