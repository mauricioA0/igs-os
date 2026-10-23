"""Payment reminder activities (task queue ``flows``): thin wrappers over ``igs_common.payments``.

``payments.queue_reminders`` reads positions in one short transaction, drafts outside any
transaction (the model call can take seconds), then writes the approvals in a second one;
``enqueue_reminders`` dedupes, so a retry after a crash between the two never doubles them.
Only counts cross the workflow boundary: amounts, names and email text stay in Postgres.
"""

from __future__ import annotations

import uuid
from collections.abc import Callable
from dataclasses import dataclass
from datetime import date
from typing import Any

from sqlalchemy.ext.asyncio import AsyncEngine
from temporalio import activity

from igs_common.db.session import configure, session_scope
from igs_common.llm import LLMClient
from igs_common.payments import draft_reminder, group_reminders
from igs_common.payments.inbox import enqueue_reminders, release_approved
from igs_common.payments.service import payment_positions


@dataclass
class PaymentRunInput:
    tenant_id: str
    today: str  # ISO date, the Buenos Aires operations day (computed by the workflow)


@dataclass
class QueueRemindersResult:
    trips: int = 0
    reminders: int = 0
    approvals_created: int = 0
    template_fallbacks: int = 0


class PaymentActivities:
    def __init__(
        self,
        *,
        engine: AsyncEngine | None = None,
        llm: LLMClient | None = None,
        llm_factory: Callable[[], LLMClient | None] | None = None,
    ) -> None:
        self._engine = engine
        self._llm = llm
        self._llm_factory = llm_factory

    def _engine_or_default(self) -> AsyncEngine:
        if self._engine is None:
            self._engine = configure()
        return self._engine

    def _get_llm(self) -> LLMClient | None:
        if self._llm is None and self._llm_factory is not None:
            self._llm = self._llm_factory()
        return self._llm

    @activity.defn(name="payments.queue_reminders")
    async def queue_reminders(self, inp: PaymentRunInput) -> QueueRemindersResult:
        tenant = uuid.UUID(inp.tenant_id)
        today = date.fromisoformat(inp.today)
        engine = self._engine_or_default()
        async with session_scope(tenant, engine=engine) as session:
            positions = await payment_positions(session, tenant_id=tenant, today=today)
        groups = group_reminders(positions, today=today)
        llm = self._get_llm()
        drafts = [(g, await draft_reminder(llm, g)) for g in groups]
        async with session_scope(tenant, engine=engine) as session:
            created = await enqueue_reminders(session, tenant_id=tenant, drafts=drafts)
        return QueueRemindersResult(
            trips=len(positions),
            reminders=len(groups),
            approvals_created=len(created),
            template_fallbacks=sum(d.source == "template" for _, d in drafts),
        )

    @activity.defn(name="payments.release_approved")
    async def release_approved(self, inp: PaymentRunInput) -> int:
        tenant = uuid.UUID(inp.tenant_id)
        async with session_scope(tenant, engine=self._engine_or_default()) as session:
            return len(await release_approved(session, tenant_id=tenant))

    def all(self) -> list[Callable[..., Any]]:
        return [self.queue_reminders, self.release_approved]
