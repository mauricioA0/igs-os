"""OpenTelemetry attributes for model calls.

The GenAI semantic conventions are still "Development" (2026-10), so every attribute name
lives here: a rename upstream touches only this module. Prompt and completion content are
never recorded on spans.
"""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from decimal import Decimal

from opentelemetry import trace
from opentelemetry.trace import Span, SpanKind, Status, StatusCode

from .types import GenerateResult, Usage

# GenAI semantic conventions
OPERATION_NAME = "gen_ai.operation.name"
PROVIDER_NAME = "gen_ai.provider.name"
REQUEST_MODEL = "gen_ai.request.model"
REQUEST_MAX_TOKENS = "gen_ai.request.max_tokens"
RESPONSE_MODEL = "gen_ai.response.model"
RESPONSE_ID = "gen_ai.response.id"
RESPONSE_FINISH_REASONS = "gen_ai.response.finish_reasons"
USAGE_INPUT_TOKENS = "gen_ai.usage.input_tokens"
USAGE_OUTPUT_TOKENS = "gen_ai.usage.output_tokens"
TOOL_NAME = "gen_ai.tool.name"
TOOL_CALL_ID = "gen_ai.tool.call.id"

# Ours, for what the spec doesn't cover yet
CACHE_READ_TOKENS = "igs.llm.cache_read_tokens"
CACHE_WRITE_TOKENS = "igs.llm.cache_write_tokens"
REASONING_TOKENS = "igs.llm.reasoning_tokens"
EFFORT = "igs.llm.effort"
COST_USD = "igs.llm.cost_usd"
LLM_ROLE = "igs.llm.role"

_tracer = trace.get_tracer("igs_common.llm")


@contextmanager
def llm_span(
    *,
    provider: str,
    model: str,
    role: str | None = None,
    operation: str = "chat",
    max_tokens: int | None = None,
    effort: str | None = None,
) -> Iterator[Span]:
    with _tracer.start_as_current_span(f"{operation} {model}", kind=SpanKind.CLIENT) as span:
        span.set_attribute(OPERATION_NAME, operation)
        span.set_attribute(PROVIDER_NAME, provider)
        span.set_attribute(REQUEST_MODEL, model)
        if role:
            span.set_attribute(LLM_ROLE, role)
        if max_tokens is not None:
            span.set_attribute(REQUEST_MAX_TOKENS, max_tokens)
        if effort:
            span.set_attribute(EFFORT, effort)
        yield span


def record_result(span: Span, result: GenerateResult) -> None:  # type: ignore[type-arg]
    span.set_attribute(RESPONSE_MODEL, result.model)
    if result.response_id:
        span.set_attribute(RESPONSE_ID, result.response_id)
    span.set_attribute(RESPONSE_FINISH_REASONS, [result.finish_reason])
    record_usage(span, result.usage, result.cost_usd)
    if result.finish_reason in ("error", "content_filter", "refusal"):
        span.set_status(Status(StatusCode.ERROR, result.finish_reason))


def record_usage(span: Span, usage: Usage, cost_usd: Decimal | None) -> None:
    span.set_attribute(USAGE_INPUT_TOKENS, usage.input_tokens)
    span.set_attribute(USAGE_OUTPUT_TOKENS, usage.output_tokens)
    span.set_attribute(CACHE_READ_TOKENS, usage.cached_input_tokens)
    span.set_attribute(CACHE_WRITE_TOKENS, usage.cache_write_tokens)
    span.set_attribute(REASONING_TOKENS, usage.reasoning_tokens)
    if cost_usd is not None:
        span.set_attribute(COST_USD, float(cost_usd))


@contextmanager
def tool_span(name: str, call_id: str) -> Iterator[Span]:
    with _tracer.start_as_current_span(f"execute_tool {name}", kind=SpanKind.INTERNAL) as span:
        span.set_attribute(OPERATION_NAME, "execute_tool")
        span.set_attribute(TOOL_NAME, name)
        span.set_attribute(TOOL_CALL_ID, call_id)
        yield span
