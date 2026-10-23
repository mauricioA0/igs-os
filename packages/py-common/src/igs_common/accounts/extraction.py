"""Interaction → account facts + stakeholder suggestions, with verified provenance.

Every fact must quote its source verbatim; anything the model can't back with an exact span of
the interaction is rejected before it reaches the database.
"""

from __future__ import annotations

import re
import unicodedata
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import date, datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, Field
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from igs_common.db.enums import FactKind, Sentiment, StakeholderRole
from igs_common.db.models import AccountFact, Stakeholder
from igs_common.llm import GenerateOptions, LLMClient, LLMError, Message, Role, Usage

from . import prompts
from .types import FactView, StakeholderView

MIN_CONFIDENCE = 0.5
MIN_EVIDENCE_CHARS = 8


class ExtractedFact(BaseModel):
    kind: FactKind
    statement: str
    evidence: str = Field(description="Verbatim span copied from the interaction.")
    confidence: float = Field(ge=0, le=1)
    severity: Literal["low", "medium", "high"] | None = Field(
        default=None, description="Risks only."
    )
    due_date: date | None = Field(default=None, description="Commitments with a stated date.")
    supersedes: list[str] = Field(
        default_factory=list, description="Labels (F1…) of existing facts this replaces."
    )


class ExtractedStakeholder(BaseModel):
    name: str
    title: str | None = None
    role: StakeholderRole
    sentiment: Sentiment
    evidence: str = Field(description="Verbatim span copied from the interaction.")


class ExtractionOutput(BaseModel):
    facts: list[ExtractedFact]
    stakeholders: list[ExtractedStakeholder]


@dataclass(frozen=True)
class InteractionInput:
    id: UUID
    account_id: UUID
    occurred_at: datetime
    channel: str
    body: str
    subject: str | None = None
    stakeholder_id: UUID | None = None
    stakeholder_name: str | None = None


@dataclass(frozen=True)
class AcceptedFact:
    kind: FactKind
    statement: str
    evidence: str
    confidence: float
    severity: str | None
    due_date: date | None
    supersedes: tuple[UUID, ...]


@dataclass(frozen=True)
class StakeholderSuggestion:
    """Shown to ops as a one-click suggestion; never applied silently."""

    name: str
    title: str | None
    role: StakeholderRole
    sentiment: Sentiment
    evidence: str
    matched_stakeholder_id: UUID | None


@dataclass(frozen=True)
class Rejection:
    item: str
    reason: str


@dataclass(frozen=True)
class ExtractionResult:
    interaction_id: UUID
    facts: tuple[AcceptedFact, ...]
    suggestions: tuple[StakeholderSuggestion, ...]
    rejected: tuple[Rejection, ...]
    model: str
    usage: Usage


async def extract(
    llm: LLMClient,
    interaction: InteractionInput,
    *,
    open_facts: Sequence[FactView] = (),
    stakeholders: Sequence[StakeholderView] = (),
) -> ExtractionResult:
    labels = {f"F{i}": fact for i, fact in enumerate(open_facts, start=1)}
    existing = "\n".join(
        f"{label}: [{fact.kind.value}] {fact.statement}" for label, fact in labels.items()
    )
    people = "\n".join(f"- {p.name} ({p.role.value})" for p in stakeholders)
    header = f"{interaction.channel} {interaction.occurred_at:%Y-%m-%d}"
    if interaction.stakeholder_name:
        header += f" · {interaction.stakeholder_name}"
    prompt = (
        f"Existing open facts:\n{existing or '(none)'}\n\n"
        f"Known stakeholders:\n{people or '(none)'}\n\n"
        f"<interaction>\n{header}\nSubject: {interaction.subject or '—'}\n\n"
        f"{interaction.body}\n</interaction>"
    )
    result = await llm.generate(
        Role.EXTRACTOR,
        [Message("user", prompt)],
        output_model=ExtractionOutput,
        options=GenerateOptions(
            instructions=prompts.EXTRACTION,
            reasoning_effort="low",
            metadata={"feature": "account360.extract", "interaction_id": str(interaction.id)},
        ),
    )
    if result.parsed is None:
        raise LLMError(f"extraction returned no structured output ({result.finish_reason})")

    source = f"{interaction.subject or ''}\n{interaction.body}"
    accepted: list[AcceptedFact] = []
    rejected: list[Rejection] = []
    seen_statements = {_normalize(f.statement) for f in open_facts}
    for fact in result.parsed.facts:
        problem = _evidence_problem(fact.evidence, source)
        if problem is None and fact.confidence < MIN_CONFIDENCE:
            problem = f"confidence {fact.confidence:.2f} below {MIN_CONFIDENCE}"
        if problem is None and _normalize(fact.statement) in seen_statements:
            problem = "duplicate of an existing fact"
        if problem is not None:
            rejected.append(Rejection(item=fact.statement, reason=problem))
            continue
        seen_statements.add(_normalize(fact.statement))
        accepted.append(
            AcceptedFact(
                kind=fact.kind,
                statement=fact.statement.strip(),
                evidence=fact.evidence.strip(),
                confidence=fact.confidence,
                severity=fact.severity if fact.kind is FactKind.RISK else None,
                due_date=fact.due_date if fact.kind is FactKind.COMMITMENT else None,
                supersedes=tuple(
                    labels[label].id for label in dict.fromkeys(fact.supersedes) if label in labels
                ),
            )
        )

    suggestions: list[StakeholderSuggestion] = []
    by_name = {_normalize(p.name): p.id for p in stakeholders}
    for person in result.parsed.stakeholders:
        problem = _evidence_problem(person.evidence, source)
        if problem is not None:
            rejected.append(Rejection(item=person.name, reason=problem))
            continue
        suggestions.append(
            StakeholderSuggestion(
                name=person.name.strip(),
                title=person.title,
                role=person.role,
                sentiment=person.sentiment,
                evidence=person.evidence.strip(),
                matched_stakeholder_id=by_name.get(_normalize(person.name)),
            )
        )

    return ExtractionResult(
        interaction_id=interaction.id,
        facts=tuple(accepted),
        suggestions=tuple(suggestions),
        rejected=tuple(rejected),
        model=result.model,
        usage=result.usage,
    )


async def apply_extraction(
    session: AsyncSession,
    *,
    tenant_id: UUID,
    interaction: InteractionInput,
    result: ExtractionResult,
) -> list[UUID]:
    """Insert accepted facts with provenance and link supersessions. Returns new fact ids.

    Stakeholder suggestions are returned to the caller (UI), not written. The only stakeholder
    field updated directly is `last_contact_at` of the interaction's own stakeholder.
    """
    new_ids: list[UUID] = []
    optional = {"severity", "due_date"} & set(AccountFact.__table__.columns.keys())
    for fact in result.facts:
        extra: dict[str, object] = {}
        if "severity" in optional and fact.severity:
            extra["severity"] = fact.severity
        if "due_date" in optional and fact.due_date:
            extra["due_date"] = fact.due_date
        row = AccountFact(
            tenant_id=tenant_id,
            account_id=interaction.account_id,
            kind=fact.kind,
            statement=fact.statement,
            confidence=fact.confidence,
            source_interaction_id=interaction.id,
            valid_from=interaction.occurred_at,
            **extra,
        )
        session.add(row)
        await session.flush()
        new_ids.append(row.id)
        if fact.supersedes:
            # Only open facts of the same account can be superseded (no cross-account edits).
            await session.execute(
                update(AccountFact)
                .where(
                    AccountFact.id.in_(fact.supersedes),
                    AccountFact.account_id == interaction.account_id,
                    AccountFact.tenant_id == tenant_id,
                    AccountFact.superseded_by.is_(None),
                )
                .values(superseded_by=row.id)
            )

    if interaction.stakeholder_id is not None:
        person = (
            await session.execute(
                select(Stakeholder).where(
                    Stakeholder.id == interaction.stakeholder_id,
                    Stakeholder.account_id == interaction.account_id,
                )
            )
        ).scalar_one_or_none()
        if person is not None and (
            person.last_contact_at is None or person.last_contact_at < interaction.occurred_at
        ):
            person.last_contact_at = interaction.occurred_at
    return new_ids


def verify_evidence(evidence: str, source: str) -> bool:
    return _evidence_problem(evidence, source) is None


def _evidence_problem(evidence: str, source: str) -> str | None:
    quote = _normalize(evidence)
    if len(quote) < MIN_EVIDENCE_CHARS:
        return "evidence too short"
    if quote not in _normalize(source):
        return "evidence is not a verbatim span of the interaction"
    return None


_QUOTES = str.maketrans({"‘": "'", "’": "'", "“": '"', "”": '"', "–": "-", "—": "-"})
_SPACE = re.compile(r"\s+")


def _normalize(text: str) -> str:
    """Whitespace, quote styles, unicode form and case don't count as changing a quote."""
    text = unicodedata.normalize("NFKC", text).translate(_QUOTES)
    return _SPACE.sub(" ", text).strip().casefold()
