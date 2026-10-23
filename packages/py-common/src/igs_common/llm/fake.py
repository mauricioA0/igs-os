"""Scripted `LLMClient` for tests: no network, deterministic, records every request."""

from __future__ import annotations

import json
from collections.abc import AsyncIterator, Sequence
from dataclasses import dataclass, field
from decimal import Decimal
from typing import Any

from pydantic import BaseModel

from .types import (
    AssistantTurn,
    Completed,
    ConversationItem,
    FinishReason,
    GenerateOptions,
    GenerateResult,
    LLMError,
    Role,
    StreamEvent,
    TextDelta,
    ToolCall,
    ToolCallReady,
    ToolCallStarted,
    ToolSpec,
    Usage,
)


@dataclass(frozen=True)
class Scripted:
    """One canned model reply. `json` is serialized into the text for structured outputs."""

    text: str = ""
    tool_calls: Sequence[tuple[str, dict[str, Any]]] = ()  # (tool name, arguments)
    json: dict[str, Any] | None = None
    finish_reason: FinishReason | None = None
    usage: Usage = field(default_factory=lambda: Usage(input_tokens=10, output_tokens=5))


@dataclass
class Request:
    role: Role
    items: list[ConversationItem]
    tools: list[str]
    output_model: type[BaseModel] | None
    options: GenerateOptions | None


class FakeLLM:
    provider = "fake"

    def __init__(self, script: Sequence[Scripted], *, models: Sequence[str] = ("fake-model",)):
        self._script = list(script)
        self._models = list(models)
        self.requests: list[Request] = []
        self._call_seq = 0

    async def generate[T: BaseModel](
        self,
        role: Role,
        items: Sequence[ConversationItem],
        *,
        output_model: type[T] | None = None,
        tools: Sequence[ToolSpec] = (),
        options: GenerateOptions | None = None,
    ) -> GenerateResult[T]:
        self.requests.append(
            Request(role, list(items), [t.name for t in tools], output_model, options)
        )
        if not self._script:
            raise LLMError("FakeLLM script exhausted")
        step = self._script.pop(0)
        calls = tuple(self._next_call(name, args) for name, args in step.tool_calls)
        text = json.dumps(step.json) if step.json is not None else step.text
        finish = step.finish_reason or ("tool_calls" if calls else "stop")
        parsed = (
            output_model.model_validate_json(text)
            if output_model is not None and finish == "stop"
            else None
        )
        return GenerateResult(
            model=self._models[0],
            turn=AssistantTurn(text=text, tool_calls=calls, provider=self.provider),
            finish_reason=finish,
            usage=step.usage,
            cost_usd=Decimal(0),
            response_id=f"fake_{len(self.requests)}",
            parsed=parsed,
        )

    async def stream(
        self,
        role: Role,
        items: Sequence[ConversationItem],
        *,
        tools: Sequence[ToolSpec] = (),
        options: GenerateOptions | None = None,
    ) -> AsyncIterator[StreamEvent]:
        result: GenerateResult[BaseModel] = await self.generate(
            role, items, tools=tools, options=options
        )
        for word in result.text.split(" ") if result.text else []:
            yield TextDelta(word + " ")
        for call in result.tool_calls:
            yield ToolCallStarted(call.call_id, call.name)
            yield ToolCallReady(call)
        yield Completed(result)

    async def list_available_models(self) -> list[str]:
        return list(self._models)

    def _next_call(self, name: str, args: dict[str, Any]) -> ToolCall:
        self._call_seq += 1
        return ToolCall(
            call_id=f"call_{self._call_seq}",
            name=name,
            arguments=args,
            raw_arguments=json.dumps(args),
        )
