"""BudgetedLLM: daily spend cap and default output ceiling (readiness review B-01)."""

from collections.abc import AsyncIterator, Sequence
from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal
from typing import Any

import pytest

from igs_common.llm import (
    BudgetedLLM,
    BudgetExceededError,
    Completed,
    GenerateOptions,
    GenerateResult,
    LLMError,
    Message,
    Role,
    TextDelta,
    Usage,
    create_llm,
)
from igs_common.llm.budget import MemorySpendStore, budget_from_env, estimate_cost
from igs_common.llm.types import AssistantTurn

DAY = date(2026, 10, 23)


@dataclass
class Recording:
    """Inner client that costs a fixed amount per call and records the options it got."""

    cost: Decimal | None = Decimal("0.40")
    provider: str = "fake"
    options: list[GenerateOptions | None] = field(default_factory=list)

    def _result(self) -> GenerateResult[Any]:
        return GenerateResult(
            turn=AssistantTurn(text="ok", tool_calls=(), provider=self.provider),
            model="fake-model",
            usage=Usage(input_tokens=1_000, output_tokens=500),
            cost_usd=self.cost,
            finish_reason="stop",
        )

    async def generate(self, role: Role, items: Sequence[Any], **kw: Any) -> GenerateResult[Any]:
        self.options.append(kw.get("options"))
        return self._result()

    async def stream(self, role: Role, items: Sequence[Any], **kw: Any) -> AsyncIterator[Any]:
        self.options.append(kw.get("options"))
        yield TextDelta("ok")
        yield Completed(self._result())

    async def list_available_models(self) -> list[str]:
        return ["fake-model"]


def _llm(inner: Recording, budget: str | None = "1.00", **kw: Any) -> BudgetedLLM:
    return BudgetedLLM(
        inner,  # type: ignore[arg-type]
        daily_budget_usd=Decimal(budget) if budget else None,
        store=kw.pop("store", MemorySpendStore()),
        today=lambda: DAY,
        **kw,
    )


MSG = [Message("user", "hi")]


async def test_refuses_once_the_day_is_spent() -> None:
    store = MemorySpendStore()
    llm = _llm(Recording(), store=store)
    for _ in range(3):  # 0.40 × 3 = 1.20: the third call starts below the cap and overshoots
        await llm.generate(Role.CHAT, MSG)
    assert await store.spent(DAY) == Decimal("1.20")
    with pytest.raises(BudgetExceededError) as exc:
        await llm.generate(Role.CHAT, MSG)
    assert isinstance(exc.value, LLMError)  # existing LLMError handlers degrade gracefully


async def test_budget_resets_with_the_day() -> None:
    store = MemorySpendStore()
    store.by_day[DAY] = Decimal("5")
    llm = _llm(Recording(), store=store)
    llm._today = lambda: date(2026, 10, 24)
    await llm.generate(Role.CHAT, MSG)


async def test_stream_is_checked_and_recorded() -> None:
    store = MemorySpendStore()
    llm = _llm(Recording(), budget="0.40", store=store)
    events = [e async for e in llm.stream(Role.AGENT, MSG)]
    assert isinstance(events[-1], Completed)
    assert await store.spent(DAY) == Decimal("0.40")
    with pytest.raises(BudgetExceededError):
        _ = [e async for e in llm.stream(Role.AGENT, MSG)]


async def test_unknown_price_is_estimated_high_not_free() -> None:
    store = MemorySpendStore()
    await _llm(Recording(cost=None), store=store).generate(Role.CHAT, MSG)
    assert await store.spent(DAY) == estimate_cost(Usage(input_tokens=1_000, output_tokens=500))
    assert await store.spent(DAY) > 0


async def test_default_output_ceiling_keeps_callers_own_value() -> None:
    inner = Recording()
    llm = _llm(inner, budget=None, max_output_tokens=1_500)
    await llm.generate(Role.CHAT, MSG)
    await llm.generate(Role.CHAT, MSG, options=GenerateOptions(instructions="x"))
    await llm.generate(Role.CHAT, MSG, options=GenerateOptions(max_output_tokens=200))
    got = [o.max_output_tokens if o else None for o in inner.options]
    assert got == [1_500, 1_500, 200]
    assert inner.options[1] is not None and inner.options[1].instructions == "x"


async def test_record_failure_does_not_fail_the_call() -> None:
    class Broken(MemorySpendStore):
        async def add(self, day: date, cost: Decimal) -> None:
            raise RuntimeError("db down")

    result = await _llm(Recording(), store=Broken()).generate(Role.CHAT, MSG)
    assert result.text == "ok"


async def test_unreadable_store_fails_open() -> None:
    class Down(MemorySpendStore):
        async def spent(self, day: date) -> Decimal:
            raise RuntimeError("relation llm_spend_daily does not exist")

    result = await _llm(Recording(), store=Down()).generate(Role.CHAT, MSG)
    assert result.text == "ok"


def test_env_parsing(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("IGS_LLM_DAILY_BUDGET_USD", raising=False)
    monkeypatch.delenv("IGS_LLM_MAX_OUTPUT_TOKENS", raising=False)
    assert budget_from_env() == (None, None)
    monkeypatch.setenv("IGS_LLM_DAILY_BUDGET_USD", "5")
    monkeypatch.setenv("IGS_LLM_MAX_OUTPUT_TOKENS", "2000")
    assert budget_from_env() == (Decimal("5"), 2000)
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test-not-real")
    assert isinstance(create_llm(), BudgetedLLM)
