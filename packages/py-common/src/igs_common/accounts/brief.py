"""Account brief: 4–6 cited sentences, cached by a hash of everything it was built from."""

from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass
from datetime import UTC, date, datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel
from sqlalchemy import func, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from igs_common.db.base import uuid7
from igs_common.db.enums import AccountHealth
from igs_common.db.models import AccountBrief
from igs_common.llm import GenerateOptions, LLMClient, LLMError, Message, Role, Usage

from . import prompts
from .health import compute_health
from .sources import CitedSentence, build_sources, resolve_citations
from .types import AccountSnapshot, Citation, HealthResult

MAX_SENTENCES = 6


class BriefOutput(BaseModel):
    sentences: list[CitedSentence]


@dataclass(frozen=True)
class Brief:
    account_id: UUID
    text: str
    citations: tuple[Citation, ...]
    health: AccountHealth
    health_reasons: tuple[str, ...]
    inputs_hash: str
    model: str
    generated_at: datetime
    dropped_sentences: int = 0
    usage: Usage = Usage()

    def to_json(self) -> dict[str, Any]:
        data = asdict(self)
        data.pop("usage")
        return json.loads(json.dumps(data, default=str))

    @classmethod
    def from_json(cls, data: dict[str, Any]) -> Brief:
        return cls(
            account_id=UUID(data["account_id"]),
            text=data["text"],
            citations=tuple(
                Citation(
                    n=c["n"],
                    interaction_id=UUID(c["interaction_id"]) if c["interaction_id"] else None,
                    label=c["label"],
                )
                for c in data["citations"]
            ),
            health=AccountHealth(data["health"]),
            health_reasons=tuple(data["health_reasons"]),
            inputs_hash=data["inputs_hash"],
            model=data["model"],
            generated_at=datetime.fromisoformat(data["generated_at"]),
            dropped_sentences=data.get("dropped_sentences", 0),
        )


def inputs_hash(snapshot: AccountSnapshot, health: HealthResult, *, today: date, model: str) -> str:
    """Changes whenever anything the brief depends on changes (and once a day for 'today')."""
    payload = {
        "prompt": prompts.PROMPT_VERSION,
        "model": model,
        "today": today.isoformat(),
        "account": [snapshot.status.value, snapshot.name],
        "health": [health.health.value, list(health.reasons)],
        "facts": sorted(
            [str(f.id), f.statement, f.status, f.severity, str(f.due_date)] for f in snapshot.facts
        ),
        "people": sorted(
            [str(p.id), p.role.value, p.sentiment.value, p.influence, str(p.last_contact_at)]
            for p in snapshot.stakeholders
        ),
        "trips": sorted(
            [str(t.id), t.status.value, str(t.start_date), str(t.total_usd), str(t.paid_usd)]
            for t in snapshot.trips
        ),
        "leads": sorted([str(lead.id), lead.status.value] for lead in snapshot.leads),
        "interactions": [str(i.id) for i in snapshot.interactions],
    }
    raw = json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str)
    return "sha256:" + hashlib.sha256(raw.encode()).hexdigest()


async def generate_brief(
    llm: LLMClient,
    snapshot: AccountSnapshot,
    *,
    today: date,
    model: str,
    role: Role = Role.AGENT,
) -> Brief:
    health = compute_health(snapshot, today=today)
    sources = build_sources(snapshot, health, today=today, interactions=snapshot.interactions)
    result = await llm.generate(
        role,
        [
            Message(
                "user", f"Fuentes:\n\n{sources.rendered}\n\nEscribí el brief de {snapshot.name}."
            )
        ],
        output_model=BriefOutput,
        options=GenerateOptions(
            instructions=prompts.BRIEF,
            reasoning_effort="low",
            cache_key=f"account-brief:{snapshot.tenant_id}",
            metadata={"feature": "account360.brief", "account_id": str(snapshot.account_id)},
        ),
    )
    if result.parsed is None:
        raise LLMError(f"brief returned no structured output ({result.finish_reason})")
    text, citations, dropped = resolve_citations(result.parsed.sentences[:MAX_SENTENCES], sources)
    dropped += max(0, len(result.parsed.sentences) - MAX_SENTENCES)
    if not text:
        raise LLMError("brief had no sentence backed by a valid source")
    return Brief(
        account_id=snapshot.account_id,
        text=text,
        citations=citations,
        health=health.health,
        health_reasons=health.reasons,
        inputs_hash=inputs_hash(snapshot, health, today=today, model=model),
        model=result.model,
        generated_at=datetime.now(UTC),
        dropped_sentences=dropped,
        usage=result.usage,
    )


async def cached_brief(
    session: AsyncSession, *, tenant_id: UUID, account_id: UUID, inputs_hash: str
) -> Brief | None:
    row = (
        await session.execute(
            select(AccountBrief.brief).where(
                AccountBrief.tenant_id == tenant_id,
                AccountBrief.account_id == account_id,
                AccountBrief.inputs_hash == inputs_hash,
            )
        )
    ).scalar_one_or_none()
    return Brief.from_json(row) if row is not None else None


async def store_brief(session: AsyncSession, *, tenant_id: UUID, brief: Brief) -> None:
    """Upsert on (tenant, account, inputs_hash): a forced refresh replaces the same-input brief."""
    stmt = insert(AccountBrief).values(
        id=uuid7(),
        tenant_id=tenant_id,
        account_id=brief.account_id,
        inputs_hash=brief.inputs_hash,
        brief=brief.to_json(),
        model=brief.model,
    )
    await session.execute(
        stmt.on_conflict_do_update(
            index_elements=[
                AccountBrief.tenant_id,
                AccountBrief.account_id,
                AccountBrief.inputs_hash,
            ],
            set_={
                "brief": stmt.excluded.brief,
                "model": stmt.excluded.model,
                "updated_at": func.now(),
            },
        )
    )
