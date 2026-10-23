from decimal import Decimal

import pytest
from pydantic import BaseModel

from igs_common.llm import (
    FakeLLM,
    LLMError,
    Message,
    ModelNotConfiguredError,
    ModelRegistry,
    PriceTable,
    Role,
    Scripted,
    ToolResult,
    ToolSpec,
    Usage,
    run_tool_loop,
    run_tool_step,
)


class FindOpponents(BaseModel):
    sport: str
    level: int


class Brief(BaseModel):
    status: str
    risks: list[str]


TOOLS = [ToolSpec("find_opponents", "Find opponents by sport and level.", FindOpponents)]


async def test_tool_loop_runs_parallel_calls_and_feeds_results_back() -> None:
    llm = FakeLLM(
        [
            Scripted(
                tool_calls=[
                    ("find_opponents", {"sport": "soccer", "level": 7}),
                    ("find_opponents", {"sport": "soccer", "level": 6}),
                ]
            ),
            Scripted(text="Two good options."),
        ]
    )
    seen: list[int] = []

    async def find(args: BaseModel) -> str:
        assert isinstance(args, FindOpponents)
        seen.append(args.level)
        return f"opponents at level {args.level}"

    items: list = [Message("user", "Find me rivals")]
    outcome, usage = await run_tool_loop(llm, Role.AGENT, items, TOOLS, {"find_opponents": find})

    assert outcome.result.text == "Two good options."
    assert sorted(seen) == [6, 7]
    results = [i for i in items if isinstance(i, ToolResult)]
    assert [r.output for r in results] == ["opponents at level 7", "opponents at level 6"]
    # Second request saw both tool results.
    assert sum(isinstance(i, ToolResult) for i in llm.requests[1].items) == 2
    assert usage == Usage(input_tokens=20, output_tokens=10)


async def test_invalid_arguments_and_handler_errors_become_error_results() -> None:
    llm = FakeLLM(
        [
            Scripted(
                tool_calls=[
                    ("find_opponents", {"sport": "soccer"}),  # missing level
                    ("find_opponents", {"sport": "soccer", "level": 5}),
                    ("unknown_tool", {}),
                ]
            )
        ]
    )

    async def boom(_: BaseModel) -> str:
        raise RuntimeError("db down")

    items: list = [Message("user", "go")]
    outcome = await run_tool_step(llm, Role.AGENT, items, TOOLS, {"find_opponents": boom})

    errors = [r for r in outcome.tool_results if r.is_error]
    assert len(errors) == 3
    assert "invalid arguments" in errors[0].output
    assert "RuntimeError: db down" in errors[1].output
    assert "unknown tool" in errors[2].output


async def test_truncated_tool_calls_are_not_executed_or_kept() -> None:
    llm = FakeLLM(
        [Scripted(tool_calls=[("find_opponents", {"sport": "x"})], finish_reason="length")]
    )
    items: list = [Message("user", "go")]

    async def never(_: BaseModel) -> str:
        raise AssertionError("must not run")

    outcome = await run_tool_step(llm, Role.AGENT, items, TOOLS, {"find_opponents": never})
    assert outcome.done
    assert len(items) == 1


async def test_structured_output_is_parsed() -> None:
    llm = FakeLLM([Scripted(json={"status": "active", "risks": ["deposit late"]})])
    result = await llm.generate(Role.EXTRACTOR, [Message("user", "brief")], output_model=Brief)
    assert result.parsed == Brief(status="active", risks=["deposit late"])


async def test_fake_script_exhaustion_raises() -> None:
    with pytest.raises(LLMError):
        await FakeLLM([]).generate(Role.CHAT, [Message("user", "hi")])


def test_registry_resolves_roles_and_reports_unknown_ids() -> None:
    registry = ModelRegistry({Role.AGENT: "model-a", Role.JUDGE: "model-j"})
    assert registry.model_for("agent") == "model-a"
    with pytest.raises(ModelNotConfiguredError):
        registry.model_for(Role.CHAT)
    assert registry.missing_from(["model-a"]) == {Role.JUDGE: "model-j"}


def test_price_table_cost_with_cache_discount() -> None:
    table = PriceTable.from_dict(
        {
            "version": "2026-10-test",
            "models": {"m": {"input": 2, "cached_input": 0.2, "output": 10}},
        }
    )
    usage = Usage(input_tokens=1_000_000, cached_input_tokens=500_000, output_tokens=100_000)
    # 500k uncached * $2 + 500k cached * $0.2 + 100k * $10, per million
    assert table.cost("m", usage) == Decimal("2.100000")
    assert table.cost("unknown", usage) is None
