"""Numbered sources for grounded generation, and validation of what the model cites.

The model only ever sees `[S0]…[Sn]` labels, never ids: S0 is the system record (SQL state),
S1…Sn are interactions. Citations are mapped back and checked before anything is shown.
"""

from __future__ import annotations

import re
from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from datetime import date
from uuid import UUID

from pydantic import BaseModel, Field

from .health import next_departure
from .types import AccountSnapshot, Citation, HealthResult, InteractionView

_MAX_SOURCE_CHARS = 1800
SYSTEM_SOURCE = 0


class CitedSentence(BaseModel):
    text: str = Field(description="One sentence, no citation markers in the text itself.")
    sources: list[int] = Field(description="Source numbers (the n in [Sn]) supporting it.")


@dataclass(frozen=True)
class SourceSet:
    """`by_n[n]` → interaction (None for S0). `rendered` is what goes into the prompt."""

    by_n: dict[int, InteractionView | None]
    rendered: str

    def label(self, n: int) -> str:
        item = self.by_n.get(n)
        if item is None:
            return "Registro del sistema (IGS OS)"
        who = f" · {item.stakeholder_name}" if item.stakeholder_name else ""
        return f"{item.channel.value} · {item.occurred_at:%d/%m/%Y}{who}"


def build_sources(
    snapshot: AccountSnapshot,
    health: HealthResult,
    *,
    today: date,
    interactions: Iterable[InteractionView] = (),
    passages: dict[UUID, str] | None = None,
) -> SourceSet:
    """S0 = structured state; then fact sources, then the given interactions (deduped).

    `passages` replaces an interaction's full body with the retrieved excerpt.
    """
    ordered: list[InteractionView] = []
    seen: set[UUID] = set()
    fact_sources = (snapshot.interaction(f.source_interaction_id) for f in snapshot.facts)
    for item in (*fact_sources, *interactions):
        if item is not None and item.id not in seen:
            seen.add(item.id)
            ordered.append(item)

    by_n: dict[int, InteractionView | None] = {SYSTEM_SOURCE: None}
    record = _system_record(snapshot, health, today)
    blocks = [f'<source id="S0" kind="system_record">\n{record}\n</source>']
    for n, item in enumerate(ordered, start=1):
        by_n[n] = item
        body = (passages or {}).get(item.id, item.body)
        header = f"{item.channel.value} {item.direction.value} {item.occurred_at:%Y-%m-%d}"
        if item.stakeholder_name:
            header += f" · {item.stakeholder_name}"
        if item.subject:
            header += f" · {item.subject}"
        blocks.append(f'<source id="S{n}" kind="interaction">\n{header}\n{_clip(body)}\n</source>')

    facts = [
        f"- [{f.kind.value}] {f.statement} (fuente: S{_n_for(by_n, f.source_interaction_id)})"
        for f in snapshot.facts
    ]
    rendered = "\n\n".join(blocks)
    if facts:
        rendered += "\n\nHechos extraídos vigentes:\n" + "\n".join(facts)
    return SourceSet(by_n=by_n, rendered=rendered)


def resolve_citations(
    sentences: Sequence[CitedSentence], sources: SourceSet
) -> tuple[str, tuple[Citation, ...], int]:
    """Keep only sentences with at least one valid source; renumber [n] by first use.

    Returns (text, citations, dropped_sentence_count).
    """
    order: dict[int, int] = {}
    parts: list[str] = []
    dropped = 0
    for sentence in sentences:
        valid = [s for s in dict.fromkeys(sentence.sources) if s in sources.by_n]
        text = _strip_markers(sentence.text)
        if not valid or not text:
            dropped += 1
            continue
        marks = []
        for s in valid:
            order.setdefault(s, len(order) + 1)
            marks.append(f"[{order[s]}]")
        parts.append(f"{text} {''.join(marks)}")
    citations = tuple(
        Citation(
            n=n,
            interaction_id=item.id if (item := sources.by_n[s]) is not None else None,
            label=sources.label(s),
        )
        for s, n in order.items()
    )
    return " ".join(parts), citations, dropped


def _system_record(snapshot: AccountSnapshot, health: HealthResult, today: date) -> str:
    lines = [
        f"Cliente: {snapshot.name} ({snapshot.kind.value}), {snapshot.location}",
        f"Estado: {snapshot.status.value}; salud: {health.health.value} — "
        + "; ".join(health.reasons),
        f"Programas: {', '.join(snapshot.sport_programs) or '—'}",
        f"Hoy: {today.isoformat()}",
    ]
    for t in snapshot.trips:
        money = ""
        if t.total_usd is not None:
            money = f"; total US$ {t.total_usd:,.0f}, pagado US$ {t.paid_usd or 0:,.0f}"
        lines.append(
            f"Gira {t.code or ''} {t.title}: {t.status.value}, {t.start_date} → {t.end_date}{money}"
        )
    upcoming = next_departure(snapshot, today=today)
    if upcoming:
        lines.append(
            f"Próxima salida: {upcoming.start_date} ({(upcoming.start_date - today).days} días)"
        )
    for lead in snapshot.leads:
        lines.append(f"Lead {lead.status.value} desde {lead.created_at:%Y-%m-%d}")
    for p in snapshot.stakeholders:
        contact = f"{p.last_contact_at:%Y-%m-%d}" if p.last_contact_at else "sin registro"
        lines.append(
            f"Persona: {p.name} — {p.title or p.role.value} ({p.role.value}), influencia "
            f"{p.influence}/5, sentimiento {p.sentiment.value}, último contacto {contact}"
        )
    return "\n".join(lines)


def _n_for(by_n: dict[int, InteractionView | None], interaction_id: UUID) -> int:
    for n, item in by_n.items():
        if item is not None and item.id == interaction_id:
            return n
    return SYSTEM_SOURCE


def _clip(text: str) -> str:
    text = text.strip()
    return text if len(text) <= _MAX_SOURCE_CHARS else text[:_MAX_SOURCE_CHARS] + " […]"


_MARKER = re.compile(r"\s*\[(?:S?\d+)(?:\]\s*\[S?\d+)*\]")


def _strip_markers(text: str) -> str:
    """Models sometimes inline `[S3]` despite instructions; markers come from `sources` only."""
    return _MARKER.sub("", text).strip()
