"""One call for every surface (API, MCP tool, scheduled job): load → build → phrase → render."""

from __future__ import annotations

from collections.abc import Callable
from contextlib import AbstractAsyncContextManager
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from igs_common.llm import LLMClient

from .build import build_digest
from .load import load_digest_inputs
from .phrase import Phrased, phrase_summary
from .render import render_html, render_json, render_text
from .types import DigestFacts, DigestRules

SessionFactory = Callable[[UUID], AbstractAsyncContextManager[AsyncSession]]


@dataclass(frozen=True)
class Digest:
    facts: DigestFacts
    phrased: Phrased
    base_url: str = ""

    def json(self) -> dict[str, Any]:
        return render_json(self.facts, self.phrased)

    def text(self) -> str:
        return render_text(self.facts, self.phrased, base_url=self.base_url)

    def html(self) -> str:
        return render_html(self.facts, self.phrased, base_url=self.base_url)


async def generate_digest(
    sessions: SessionFactory,
    *,
    tenant_id: UUID,
    llm: LLMClient | None,
    now: datetime | None = None,
    base_url: str = "",
    rules: DigestRules | None = None,
) -> Digest:
    now = now or datetime.now(UTC)
    async with sessions(tenant_id) as session:
        inputs = await load_digest_inputs(session, tenant_id=tenant_id, now=now)
    facts = build_digest(inputs, now=now, rules=rules)
    phrased = await phrase_summary(llm, facts)
    return Digest(facts=facts, phrased=phrased, base_url=base_url.rstrip("/"))
