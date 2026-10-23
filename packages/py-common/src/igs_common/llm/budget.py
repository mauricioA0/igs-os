"""Deployment-wide daily spend cap and output ceiling for model calls.

The public demo is anonymous and sits behind Vercel, whose egress IPs rotate: per-IP rate
limits alone can't bound the provider bill. `BudgetedLLM` wraps any `LLMClient` and

- refuses calls once today's spend (UTC) reaches ``IGS_LLM_DAILY_BUDGET_USD``, raising
  `BudgetExceededError` (an `LLMError`, so existing callers degrade the way they already do);
- fills ``max_output_tokens`` with ``IGS_LLM_MAX_OUTPUT_TOKENS`` when a caller didn't set one.

Spend lives in Postgres (``llm_spend_daily``), shared by the API and every worker. The check
happens before a call and the cost is added after it, so concurrent calls can overshoot the cap
by at most one call each; the cap is a fuse, not an invoice.
"""

from __future__ import annotations

import dataclasses
import logging
import os
from collections.abc import AsyncIterator, Callable, Sequence
from datetime import UTC, date, datetime
from decimal import Decimal
from typing import TYPE_CHECKING, Protocol

from pydantic import BaseModel

from .protocol import LLMClient
from .types import (
    Completed,
    ConversationItem,
    GenerateOptions,
    GenerateResult,
    LLMError,
    Role,
    StreamEvent,
    ToolSpec,
    Usage,
)

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncEngine

log = logging.getLogger(__name__)

# Used when the price table doesn't know a model: deliberately high, so a missing price
# can't switch the cap off.
FALLBACK_USD_PER_MTOK = Decimal("20")


class BudgetExceededError(LLMError):
    """Today's model budget is spent; no call was made."""


class SpendStore(Protocol):
    async def spent(self, day: date) -> Decimal: ...

    async def add(self, day: date, cost: Decimal) -> None: ...


class MemorySpendStore:
    """Per-process spend (tests and local runs without a database)."""

    def __init__(self) -> None:
        self.by_day: dict[date, Decimal] = {}

    async def spent(self, day: date) -> Decimal:
        return self.by_day.get(day, Decimal(0))

    async def add(self, day: date, cost: Decimal) -> None:
        self.by_day[day] = self.by_day.get(day, Decimal(0)) + cost


class PgSpendStore:
    """``llm_spend_daily`` (migration 0005), via the process-wide engine unless given one."""

    def __init__(self, engine: AsyncEngine | None = None) -> None:
        self._engine = engine

    async def spent(self, day: date) -> Decimal:
        from sqlalchemy import text

        from igs_common.db.session import system_scope

        async with system_scope(engine=self._engine) as session:
            value = await session.scalar(
                text("SELECT cost_usd FROM llm_spend_daily WHERE day = :day"), {"day": day}
            )
        return Decimal(value or 0)

    async def add(self, day: date, cost: Decimal) -> None:
        from sqlalchemy import text

        from igs_common.db.session import system_scope

        async with system_scope(engine=self._engine) as session:
            await session.execute(
                text(
                    "INSERT INTO llm_spend_daily (day, cost_usd, calls) VALUES (:day, :cost, 1) "
                    "ON CONFLICT (day) DO UPDATE SET cost_usd = llm_spend_daily.cost_usd + "
                    "EXCLUDED.cost_usd, calls = llm_spend_daily.calls + 1, updated_at = now()"
                ),
                {"day": day, "cost": cost},
            )


def _utc_today() -> date:
    return datetime.now(UTC).date()


def estimate_cost(usage: Usage) -> Decimal:
    tokens = usage.input_tokens + usage.output_tokens
    return FALLBACK_USD_PER_MTOK * tokens / Decimal(1_000_000)


class BudgetedLLM:
    """An `LLMClient` that enforces a daily spend cap and a default output ceiling."""

    def __init__(
        self,
        inner: LLMClient,
        *,
        daily_budget_usd: Decimal | None,
        max_output_tokens: int | None = None,
        store: SpendStore | None = None,
        today: Callable[[], date] = _utc_today,
    ) -> None:
        self.inner = inner
        self.provider = inner.provider
        self.daily_budget_usd = daily_budget_usd
        self.max_output_tokens = max_output_tokens
        self.store = store or PgSpendStore()
        self._today = today

    async def _check(self) -> None:
        if self.daily_budget_usd is None:
            return
        try:
            spent = await self.store.spent(self._today())
        except Exception:  # fail open: a bookkeeping outage shouldn't take the product down
            log.exception("llm_budget_check_failed")
            return
        if spent >= self.daily_budget_usd:
            raise BudgetExceededError(
                f"daily model budget of US${self.daily_budget_usd} reached; try again tomorrow"
            )

    async def _record(self, result: GenerateResult) -> None:  # type: ignore[type-arg]
        if self.daily_budget_usd is None:
            return
        cost = result.cost_usd if result.cost_usd is not None else estimate_cost(result.usage)
        try:
            await self.store.add(self._today(), cost)
        except Exception:  # the call already happened; never fail it over bookkeeping
            log.exception("llm_spend_record_failed")

    def _options(self, options: GenerateOptions | None) -> GenerateOptions | None:
        if self.max_output_tokens is None:
            return options
        options = options or GenerateOptions()
        if options.max_output_tokens is None:
            return dataclasses.replace(options, max_output_tokens=self.max_output_tokens)
        return options

    async def generate[T: BaseModel](
        self,
        role: Role,
        items: Sequence[ConversationItem],
        *,
        output_model: type[T] | None = None,
        tools: Sequence[ToolSpec] = (),
        options: GenerateOptions | None = None,
    ) -> GenerateResult[T]:
        await self._check()
        result = await self.inner.generate(
            role, items, output_model=output_model, tools=tools, options=self._options(options)
        )
        await self._record(result)
        return result

    async def stream(
        self,
        role: Role,
        items: Sequence[ConversationItem],
        *,
        tools: Sequence[ToolSpec] = (),
        options: GenerateOptions | None = None,
    ) -> AsyncIterator[StreamEvent]:
        await self._check()
        async for event in self.inner.stream(
            role, items, tools=tools, options=self._options(options)
        ):
            if isinstance(event, Completed):
                await self._record(event.result)
            yield event

    async def list_available_models(self) -> list[str]:
        return await self.inner.list_available_models()


def budget_from_env() -> tuple[Decimal | None, int | None]:
    """(``IGS_LLM_DAILY_BUDGET_USD``, ``IGS_LLM_MAX_OUTPUT_TOKENS``); unset or empty → None."""
    raw_budget = os.environ.get("IGS_LLM_DAILY_BUDGET_USD", "").strip()
    raw_tokens = os.environ.get("IGS_LLM_MAX_OUTPUT_TOKENS", "").strip()
    return (Decimal(raw_budget) if raw_budget else None, int(raw_tokens) if raw_tokens else None)
