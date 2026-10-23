"""One entry point for the API and MCP: briefs (cached) and questions about an account."""

from __future__ import annotations

from collections.abc import Callable
from contextlib import AbstractAsyncContextManager
from datetime import UTC, date, datetime
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from igs_common.llm import LLMClient, Role

from .ask import Answer, PassageRetriever, ask
from .brief import Brief, cached_brief, generate_brief, inputs_hash, store_brief
from .health import compute_health
from .snapshot import load_snapshot
from .types import AccountNotFoundError

SessionFactory = Callable[[UUID], AbstractAsyncContextManager[AsyncSession]]
ModelResolver = Callable[[Role], str]


class AccountIntelligence:
    def __init__(
        self,
        *,
        llm: LLMClient,
        retriever: PassageRetriever,
        session_factory: SessionFactory,
        model_for: ModelResolver,
        today: Callable[[], date] | None = None,
    ) -> None:
        self._llm = llm
        self._retriever = retriever
        self._sessions = session_factory
        self._model_for = model_for
        self._today = today or (lambda: datetime.now(UTC).date())

    async def brief(
        self, *, tenant_id: UUID, account_id: UUID, refresh: bool = False
    ) -> tuple[Brief, bool]:
        """(brief, served_from_cache). Regenerates only when its inputs changed or on refresh."""
        today = self._today()
        async with self._sessions(tenant_id) as session:
            snapshot = await load_snapshot(
                session, tenant_id=tenant_id, account_id=account_id, today=today
            )
            if snapshot is None:
                raise AccountNotFoundError(str(account_id))
            model = self._model_for(Role.AGENT)
            key = inputs_hash(
                snapshot, compute_health(snapshot, today=today), today=today, model=model
            )
            if not refresh:
                hit = await cached_brief(
                    session, tenant_id=tenant_id, account_id=account_id, inputs_hash=key
                )
                if hit is not None:
                    return hit, True
            brief = await generate_brief(self._llm, snapshot, today=today, model=model)
            await store_brief(session, tenant_id=tenant_id, brief=brief)
            return brief, False

    async def ask(self, *, tenant_id: UUID, account_id: UUID, question: str) -> Answer:
        async with self._sessions(tenant_id) as session:
            snapshot = await load_snapshot(
                session, tenant_id=tenant_id, account_id=account_id, today=self._today()
            )
            if snapshot is None:
                raise AccountNotFoundError(str(account_id))
            return await ask(
                self._llm, self._retriever, session, snapshot, question, today=self._today()
            )
