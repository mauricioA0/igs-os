"""Header → field mapping: exact names and aliases first, then (optionally) an LLM.

The LLM only ever sees header names and the *shape* of each column ("date-like", "email-like",
"number", "short text"), never cell values: rosters hold minors' data, and a mapper that can't
see values can't invent them. Its suggestions are checked against the spec and kept only above
a confidence threshold; everything is reported so ops can fix the header and re-run.
"""

from __future__ import annotations

import re
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import date, datetime
from typing import Literal

from pydantic import BaseModel, Field

from igs_common.importer.parse import Cell, Sheet, normalize
from igs_common.importer.schema import SPECS, EntitySpec
from igs_common.llm import GenerateOptions, LLMClient, Message, Role

MIN_CONFIDENCE = 0.6

Source = Literal["exact", "alias", "llm"]


@dataclass(frozen=True)
class ColumnMatch:
    header: str
    field: str | None
    source: Source | None = None
    confidence: float = 1.0
    reason: str | None = None


@dataclass(frozen=True)
class SheetMapping:
    columns: tuple[ColumnMatch, ...]

    def index_of(self) -> dict[str, int]:
        """field → column index, for the mapped columns."""
        return {c.field: i for i, c in enumerate(self.columns) if c.field is not None}

    @property
    def unmapped(self) -> list[str]:
        return [c.header for c in self.columns if c.field is None and c.header]


def match_headers(spec: EntitySpec, headers: Sequence[str]) -> SheetMapping:
    """Deterministic pass. Each field is used once; forbidden columns are never mapped."""
    lookup: dict[str, tuple[str, Source]] = {}
    for f in spec.fields:
        for alias in f.aliases:
            lookup.setdefault(normalize(alias), (f.name, "alias"))
    for f in spec.fields:  # exact names win over another field's alias
        lookup[normalize(f.name)] = (f.name, "exact")
    taken: set[str] = set()
    columns: list[ColumnMatch] = []
    for header in headers:
        norm = normalize(header)
        hit = lookup.get(norm)
        if norm in spec.forbidden and (hit is None or hit[1] != "exact"):
            columns.append(ColumnMatch(header, None, reason="forbidden"))
        elif hit and hit[0] not in taken:
            taken.add(hit[0])
            columns.append(ColumnMatch(header, hit[0], hit[1]))
        else:
            columns.append(ColumnMatch(header, None))
    return SheetMapping(tuple(columns))


def column_shape(values: Sequence[Cell]) -> str:
    """A value-free description of a column, safe to send to a model."""
    seen = [v for v in values if v not in (None, "")][:20]
    if not seen:
        return "empty"
    kinds: set[str] = set()
    for v in seen:
        if isinstance(v, bool):
            kinds.add("boolean")
        elif isinstance(v, (date, datetime)):
            kinds.add("date")
        elif isinstance(v, (int, float)):
            kinds.add("number")
        else:
            s = str(v)
            if "@" in s and "." in s.split("@")[-1]:
                kinds.add("email-like")
            elif re.fullmatch(r"\d{1,4}[-/.]\d{1,2}[-/.]\d{1,4}", s):
                kinds.add("date-like")
            elif re.fullmatch(r"(us\$|u\$s|\$|usd)?\s*[\d.,]+\s*(usd)?", s.lower()):
                kinds.add("money-or-number")
            elif s.lower() in {"yes", "no", "si", "sí", "true", "false", "x"}:
                kinds.add("yes/no")
            elif len(s) <= 24:
                kinds.add("short text")
            else:
                kinds.add("long text")
    distinct = len({str(v).lower() for v in seen})
    variety = "few distinct values" if distinct <= max(3, len(seen) // 4) else "varied values"
    return f"{', '.join(sorted(kinds))}; {variety}"


class _Suggestion(BaseModel):
    header: str
    field: str | None = Field(description="Target field name, or null if none fits.")
    confidence: float = Field(ge=0, le=1)
    reason: str = Field(max_length=200)


class _MapperOutput(BaseModel):
    columns: list[_Suggestion]


_INSTRUCTIONS = """You map spreadsheet column headers to the fields of a fixed import schema.
You see header names and a description of each column's value shape, never the values.
Rules:
- Only use field names from the schema; never invent fields.
- Each field can be used by at most one header.
- Return null when no field clearly fits. Wrong mappings are worse than unmapped columns.
- confidence is your probability that the mapping is correct.
Return one entry per header you were given, with the header exactly as written."""


async def suggest_with_llm(
    llm: LLMClient,
    spec: EntitySpec,
    sheet: Sheet,
    mapping: SheetMapping,
    *,
    min_confidence: float = MIN_CONFIDENCE,
) -> SheetMapping:
    """Ask the model about the columns the deterministic pass left unmapped."""
    pending = [
        (i, c.header)
        for i, c in enumerate(mapping.columns)
        if c.field is None and c.header and c.reason != "forbidden"
    ]
    free = [f for f in spec.fields if f.name not in mapping.index_of()]
    if not pending or not free:
        return mapping
    schema = "\n".join(f"- {f.name} ({f.type.value}): {f.description}" for f in free)
    cols = "\n".join(
        f'- "{header}": {column_shape([cells[i] for _, cells in sheet.rows])}'
        for i, header in pending
    )
    prompt = (
        f"Sheet: {spec.entity.value} — {spec.description}\n\nSchema fields still unmapped:\n"
        f"{schema}\n\nColumns to map:\n{cols}"
    )
    result = await llm.generate(
        Role.FAST,
        [Message("user", prompt)],
        output_model=_MapperOutput,
        options=GenerateOptions(
            instructions=_INSTRUCTIONS,
            metadata={"feature": "importer.map_columns", "entity": spec.entity.value},
        ),
    )
    if result.parsed is None:
        return mapping
    allowed = {f.name for f in free}
    by_header = {header: i for i, header in pending}
    best: dict[str, tuple[int, _Suggestion]] = {}
    for s in result.parsed.columns:
        idx = by_header.get(s.header)
        if idx is None or s.field not in allowed or s.confidence < min_confidence:
            continue
        current = best.get(s.field)  # type: ignore[arg-type]
        if current is None or s.confidence > current[1].confidence:
            best[s.field] = (idx, s)  # type: ignore[index]
    columns = list(mapping.columns)
    for field_name, (idx, s) in best.items():
        columns[idx] = ColumnMatch(
            columns[idx].header, field_name, "llm", round(s.confidence, 2), s.reason
        )
    return SheetMapping(tuple(columns))


def spec_for(sheet: Sheet) -> EntitySpec | None:
    return SPECS[sheet.entity] if sheet.entity is not None else None
