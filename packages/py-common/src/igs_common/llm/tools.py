"""One step of a tool-calling loop: call the model, run the tools it asked for, append results.

The full agent runtime (approvals, tool classes, persistence) lives elsewhere; this is the
provider-agnostic primitive it builds on.
"""

from __future__ import annotations

import asyncio
import time
from collections.abc import Awaitable, Callable, Mapping, Sequence
from dataclasses import dataclass, field

from pydantic import BaseModel, ValidationError

from .protocol import LLMClient
from .telemetry import tool_span
from .types import (
    ConversationItem,
    GenerateOptions,
    GenerateResult,
    Role,
    ToolCall,
    ToolResult,
    ToolSpec,
    Usage,
)

ToolHandler = Callable[[BaseModel], Awaitable[str]]


@dataclass
class StepOutcome:
    result: GenerateResult[BaseModel]
    tool_results: list[ToolResult] = field(default_factory=list)

    @property
    def done(self) -> bool:
        """True when there is nothing left to run: a final answer or an abnormal stop."""
        return not self.tool_results


async def run_tool_step(
    client: LLMClient,
    role: Role,
    items: list[ConversationItem],
    tools: Sequence[ToolSpec],
    handlers: Mapping[str, ToolHandler],
    *,
    options: GenerateOptions | None = None,
) -> StepOutcome:
    """Call the model once; execute requested tools concurrently; extend `items` in place.

    Tool failures and invalid arguments become `is_error` results the model can react to;
    they never raise. Results keep the order the model requested them in.
    """
    result = await client.generate(role, items, tools=tools, options=options)
    if result.tool_calls and result.finish_reason != "tool_calls":
        # Truncated or filtered mid-call: arguments may be partial, so never run them, and
        # don't keep a turn whose calls would have no outputs (providers reject that).
        return StepOutcome(result=result)
    items.append(result.turn)
    if not result.tool_calls:
        return StepOutcome(result=result)

    specs = {spec.name: spec for spec in tools}
    tool_results = await asyncio.gather(
        *(_run_one(call, specs, handlers) for call in result.tool_calls)
    )
    items.extend(tool_results)
    return StepOutcome(result=result, tool_results=list(tool_results))


async def run_tool_loop(
    client: LLMClient,
    role: Role,
    items: list[ConversationItem],
    tools: Sequence[ToolSpec],
    handlers: Mapping[str, ToolHandler],
    *,
    max_steps: int = 8,
    options: GenerateOptions | None = None,
) -> tuple[StepOutcome, Usage]:
    """Repeat `run_tool_step` until the model stops calling tools or `max_steps` is hit."""
    usage = Usage()
    outcome: StepOutcome | None = None
    for _ in range(max_steps):
        outcome = await run_tool_step(client, role, items, tools, handlers, options=options)
        usage = usage + outcome.result.usage
        if outcome.done:
            break
    assert outcome is not None
    return outcome, usage


async def _run_one(
    call: ToolCall, specs: Mapping[str, ToolSpec], handlers: Mapping[str, ToolHandler]
) -> ToolResult:
    spec, handler = specs.get(call.name), handlers.get(call.name)
    if spec is None or handler is None:
        return ToolResult(call.call_id, f"unknown tool {call.name!r}", is_error=True)
    with tool_span(call.name, call.call_id) as span:
        started = time.perf_counter()
        try:
            args = spec.input_model.model_validate(call.arguments)
        except ValidationError as exc:
            return ToolResult(call.call_id, f"invalid arguments: {exc.errors()}", is_error=True)
        try:
            output = await handler(args)
        except Exception as exc:  # noqa: BLE001 - surfaced to the model, not swallowed
            span.record_exception(exc)
            return ToolResult(call.call_id, f"{type(exc).__name__}: {exc}", is_error=True)
        finally:
            span.set_attribute("igs.tool.duration_ms", (time.perf_counter() - started) * 1000)
        return ToolResult(call.call_id, output)
