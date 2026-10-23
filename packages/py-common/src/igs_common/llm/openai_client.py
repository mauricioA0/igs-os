"""OpenAI implementation of `LLMClient`, on the Responses API (openai SDK 3.x)."""

from __future__ import annotations

import json
from collections.abc import AsyncIterator, Sequence
from typing import Any, cast

import openai
from openai import AsyncOpenAI
from openai.lib._pydantic import to_strict_json_schema
from openai.types.responses import (
    Response,
    ResponseCompletedEvent,
    ResponseFailedEvent,
    ResponseIncompleteEvent,
)
from pydantic import BaseModel, ValidationError

from .pricing import PriceTable
from .registry import ModelRegistry
from .settings import LLMSettings
from .telemetry import llm_span, record_result
from .types import (
    AssistantTurn,
    Completed,
    ConversationItem,
    FinishReason,
    GenerateOptions,
    GenerateResult,
    LLMError,
    Message,
    Role,
    StreamEvent,
    TextDelta,
    ToolCall,
    ToolCallReady,
    ToolCallStarted,
    ToolResult,
    ToolSpec,
    Usage,
)

PROVIDER = "openai"
_TERMINAL_EVENTS = (ResponseCompletedEvent, ResponseIncompleteEvent, ResponseFailedEvent)


class OpenAILLM:
    provider = PROVIDER

    def __init__(
        self,
        settings: LLMSettings,
        *,
        client: AsyncOpenAI | None = None,
        registry: ModelRegistry | None = None,
        prices: PriceTable | None = None,
    ) -> None:
        self._settings = settings
        self._client = client or AsyncOpenAI(
            api_key=settings.openai_api_key.get_secret_value() if settings.openai_api_key else None,
            base_url=settings.openai_base_url,
            timeout=settings.timeout_s,
            max_retries=settings.max_retries,  # SDK retries 408/409/429/5xx + connection errors
        )
        self._registry = registry or ModelRegistry(settings.models)
        self._prices = prices or PriceTable.load(settings.prices_file)

    # ── LLMClient ─────────────────────────────────────────────────────────

    async def generate[T: BaseModel](
        self,
        role: Role,
        items: Sequence[ConversationItem],
        *,
        output_model: type[T] | None = None,
        tools: Sequence[ToolSpec] = (),
        options: GenerateOptions | None = None,
    ) -> GenerateResult[T]:
        opts = options or GenerateOptions()
        model = self._registry.model_for(role)
        params = self._params(model, items, tools, opts)
        with llm_span(
            provider=PROVIDER,
            model=model,
            role=role,
            max_tokens=opts.max_output_tokens,
            effort=opts.reasoning_effort,
        ) as span:
            try:
                if output_model is not None:
                    response = await self._client.responses.parse(
                        text_format=output_model, **params
                    )
                else:
                    response = await self._client.responses.create(**params)
            except openai.APIError as exc:
                raise LLMError(f"openai request failed: {exc}") from exc
            result = self._to_result(response, output_model)
            record_result(span, result)
            return result

    async def stream(
        self,
        role: Role,
        items: Sequence[ConversationItem],
        *,
        tools: Sequence[ToolSpec] = (),
        options: GenerateOptions | None = None,
    ) -> AsyncIterator[StreamEvent]:
        opts = options or GenerateOptions()
        model = self._registry.model_for(role)
        params = self._params(model, items, tools, opts)
        with llm_span(
            provider=PROVIDER,
            model=model,
            role=role,
            max_tokens=opts.max_output_tokens,
            effort=opts.reasoning_effort,
        ) as span:
            try:
                events = await self._client.responses.create(stream=True, **params)
                async for event in events:
                    if event.type == "response.output_text.delta":
                        yield TextDelta(event.delta)
                    elif event.type == "response.output_item.added":
                        if event.item.type == "function_call":
                            yield ToolCallStarted(event.item.call_id, event.item.name)
                    elif event.type == "response.output_item.done":
                        if event.item.type == "function_call":
                            yield ToolCallReady(
                                _tool_call(
                                    event.item.call_id, event.item.name, event.item.arguments
                                )
                            )
                    elif isinstance(event, _TERMINAL_EVENTS):
                        result: GenerateResult[BaseModel] = self._to_result(event.response, None)
                        record_result(span, result)
                        yield Completed(result)
                        return
                    elif event.type == "error":
                        raise LLMError(f"openai stream error: {event.message}")
            except openai.APIError as exc:
                raise LLMError(f"openai request failed: {exc}") from exc
        raise LLMError("openai stream ended without a terminal event")

    async def list_available_models(self) -> list[str]:
        try:
            return sorted([model.id async for model in self._client.models.list()])
        except openai.APIError as exc:
            raise LLMError(f"openai models.list failed: {exc}") from exc

    # ── Request building ──────────────────────────────────────────────────

    def _params(
        self,
        model: str,
        items: Sequence[ConversationItem],
        tools: Sequence[ToolSpec],
        opts: GenerateOptions,
    ) -> dict[str, Any]:
        params: dict[str, Any] = {
            "model": model,
            "input": to_input_items(items),
            "store": self._settings.store_responses,
            "timeout": opts.timeout_s or self._settings.timeout_s,
        }
        if not self._settings.store_responses:
            # Reasoning items must round-trip between tool calls; without server-side
            # storage they come back encrypted and we replay them verbatim.
            params["include"] = ["reasoning.encrypted_content"]
        if opts.instructions:
            params["instructions"] = opts.instructions
        if opts.max_output_tokens:
            params["max_output_tokens"] = opts.max_output_tokens
        if opts.reasoning_effort:
            params["reasoning"] = {"effort": opts.reasoning_effort}
        if opts.metadata:
            params["metadata"] = opts.metadata
        if opts.cache_key:
            params["prompt_cache_key"] = opts.cache_key
        if tools:
            params["tools"] = [to_function_tool(t) for t in tools]
            params["parallel_tool_calls"] = opts.parallel_tool_calls
        return params

    # ── Response mapping ──────────────────────────────────────────────────

    def _to_result[T: BaseModel](
        self, response: Response, output_model: type[T] | None
    ) -> GenerateResult[T]:
        if response.status == "failed":
            message = response.error.message if response.error else "unknown error"
            raise LLMError(f"openai response failed: {message}")

        text_parts: list[str] = []
        calls: list[ToolCall] = []
        refusal: str | None = None
        for item in response.output:
            if item.type == "message":
                for content in item.content:
                    if content.type == "output_text":
                        text_parts.append(content.text)
                    elif content.type == "refusal":
                        refusal = content.refusal
            elif item.type == "function_call":
                calls.append(_tool_call(item.call_id, item.name, item.arguments))

        finish = _finish_reason(response, has_calls=bool(calls), refused=refusal is not None)
        usage = _usage(response)
        turn = AssistantTurn(
            text="".join(text_parts),
            tool_calls=tuple(calls),
            provider=PROVIDER,
            provider_items=tuple(
                item.model_dump(mode="json", exclude_none=True, by_alias=True)
                for item in response.output
            ),
        )
        parsed: T | None = None
        if output_model is not None and finish == "stop":
            parsed = cast(T | None, getattr(response, "output_parsed", None))
            if parsed is None and turn.text:
                try:
                    parsed = output_model.model_validate_json(turn.text)
                except ValidationError as exc:
                    raise LLMError(f"structured output did not match schema: {exc}") from exc
        return GenerateResult(
            model=response.model,
            turn=turn,
            finish_reason=finish,
            usage=usage,
            cost_usd=self._prices.cost(response.model, usage),
            response_id=response.id,
            parsed=parsed,
            refusal=refusal,
        )


# ── Pure translation helpers (unit-tested directly) ───────────────────────


def to_function_tool(spec: ToolSpec) -> dict[str, Any]:
    schema = to_strict_json_schema(spec.input_model)
    # Strict mode rejects free-form objects (`dict[str, Any]` fields such as a flow test payload
    # or approval params): the whole request fails with a 400. Those tools go non-strict; the
    # pydantic input model still validates the arguments before anything runs.
    strict = _strict_compatible(schema)
    return {
        "type": "function",
        "name": spec.name,
        "description": spec.description,
        "parameters": schema if strict else spec.input_model.model_json_schema(),
        "strict": strict,
    }


def _strict_compatible(schema: Any) -> bool:
    if isinstance(schema, list):
        return all(_strict_compatible(s) for s in schema)
    if not isinstance(schema, dict):
        return True
    if schema.get("type") == "object" and schema.get("additionalProperties") is not False:
        return False
    return all(_strict_compatible(v) for v in schema.values() if isinstance(v, dict | list))


def to_input_items(items: Sequence[ConversationItem]) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for item in items:
        if isinstance(item, Message):
            out.append({"role": item.role, "content": item.content})
        elif isinstance(item, AssistantTurn):
            if item.provider == PROVIDER and item.provider_items:
                # Output items are valid input items: replay them as returned.
                out.extend(dict(i) for i in item.provider_items)
                continue
            if item.text:
                out.append({"role": "assistant", "content": item.text})
            out.extend(
                {
                    "type": "function_call",
                    "call_id": call.call_id,
                    "name": call.name,
                    "arguments": call.raw_arguments or json.dumps(call.arguments),
                }
                for call in item.tool_calls
            )
        elif isinstance(item, ToolResult):
            output = f"ERROR: {item.output}" if item.is_error else item.output
            out.append({"type": "function_call_output", "call_id": item.call_id, "output": output})
    return out


def _tool_call(call_id: str, name: str, raw: str) -> ToolCall:
    try:
        arguments = json.loads(raw) if raw else {}
    except json.JSONDecodeError:
        arguments = {}
    if not isinstance(arguments, dict):
        arguments = {}
    return ToolCall(call_id=call_id, name=name, arguments=arguments, raw_arguments=raw)


def _finish_reason(response: Response, *, has_calls: bool, refused: bool) -> FinishReason:
    if response.status == "incomplete":
        reason = response.incomplete_details.reason if response.incomplete_details else None
        return "content_filter" if reason == "content_filter" else "length"
    if refused:
        return "refusal"
    return "tool_calls" if has_calls else "stop"


def _usage(response: Response) -> Usage:
    u = response.usage
    if u is None:
        return Usage()
    # Detail fields are optional on the wire (models without caching/reasoning omit them):
    # treat a missing count as 0 so cost math never sees None.
    inp, out = u.input_tokens_details, u.output_tokens_details
    return Usage(
        input_tokens=u.input_tokens or 0,
        cached_input_tokens=getattr(inp, "cached_tokens", None) or 0,
        cache_write_tokens=getattr(inp, "cache_write_tokens", None) or 0,
        output_tokens=u.output_tokens or 0,
        reasoning_tokens=getattr(out, "reasoning_tokens", None) or 0,
    )
