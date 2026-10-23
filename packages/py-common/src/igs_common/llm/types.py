"""Provider-agnostic shapes for model calls.

Agents, flow nodes and evals only see these types; provider adapters translate them.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal
from enum import StrEnum
from typing import Any, Literal

from pydantic import BaseModel


class Role(StrEnum):
    """What a model is used for. Each role maps to a model id in settings."""

    AGENT = "agent"  # ops copilot and agent flow nodes (tool use, multi-step)
    CHAT = "chat"  # coach-facing conversation
    EXTRACTOR = "extractor"  # structured extraction (Account 360 facts, inquiry fields)
    JUDGE = "judge"  # eval grader
    SIMULATOR = "simulator"  # eval persona simulating a coach / operator
    FAST = "fast"  # cheap flow nodes: extract, classify, capture slot filling
    REASONING = "reasoning"  # hard flow nodes that opt into the expensive model


FinishReason = Literal["stop", "tool_calls", "length", "content_filter", "refusal", "error"]


@dataclass(frozen=True)
class Message:
    role: Literal["user", "assistant", "developer"]
    content: str


@dataclass(frozen=True)
class ToolCall:
    """A tool call requested by the model. `arguments` is already JSON-decoded."""

    call_id: str
    name: str
    arguments: dict[str, Any]
    raw_arguments: str = ""


@dataclass(frozen=True)
class ToolResult:
    call_id: str
    output: str
    is_error: bool = False


@dataclass(frozen=True)
class AssistantTurn:
    """What the model produced in one call, kept so the next call can replay it.

    `provider_items` holds the provider's raw output items (e.g. OpenAI reasoning and
    function_call items). Adapters replay them verbatim when the next call goes to the
    same provider, so reasoning state survives tool-call round trips.
    """

    text: str
    tool_calls: tuple[ToolCall, ...] = ()
    provider: str = ""
    provider_items: tuple[dict[str, Any], ...] = ()


ConversationItem = Message | AssistantTurn | ToolResult


@dataclass(frozen=True)
class ToolSpec:
    """A tool the model may call. Arguments are validated against `input_model`."""

    name: str
    description: str
    input_model: type[BaseModel]


@dataclass(frozen=True)
class Usage:
    input_tokens: int = 0
    cached_input_tokens: int = 0
    cache_write_tokens: int = 0
    output_tokens: int = 0
    reasoning_tokens: int = 0

    def __add__(self, other: Usage) -> Usage:
        return Usage(
            input_tokens=self.input_tokens + other.input_tokens,
            cached_input_tokens=self.cached_input_tokens + other.cached_input_tokens,
            cache_write_tokens=self.cache_write_tokens + other.cache_write_tokens,
            output_tokens=self.output_tokens + other.output_tokens,
            reasoning_tokens=self.reasoning_tokens + other.reasoning_tokens,
        )


@dataclass(frozen=True)
class GenerateResult[T: BaseModel]:
    model: str
    turn: AssistantTurn
    finish_reason: FinishReason
    usage: Usage
    cost_usd: Decimal | None  # None when the model is missing from the price table
    response_id: str | None = None
    parsed: T | None = None
    refusal: str | None = None

    @property
    def text(self) -> str:
        return self.turn.text

    @property
    def tool_calls(self) -> tuple[ToolCall, ...]:
        return self.turn.tool_calls


# ── Streaming ──────────────────────────────────────────────────────────────


@dataclass(frozen=True)
class TextDelta:
    delta: str
    type: Literal["text_delta"] = "text_delta"


@dataclass(frozen=True)
class ToolCallStarted:
    call_id: str
    name: str
    type: Literal["tool_call_started"] = "tool_call_started"


@dataclass(frozen=True)
class ToolCallReady:
    call: ToolCall
    type: Literal["tool_call_ready"] = "tool_call_ready"


@dataclass(frozen=True)
class Completed:
    result: GenerateResult[Any]
    type: Literal["completed"] = "completed"


StreamEvent = TextDelta | ToolCallStarted | ToolCallReady | Completed


@dataclass(frozen=True)
class GenerateOptions:
    """Per-call knobs. Anything unset falls back to the provider default."""

    instructions: str | None = None
    max_output_tokens: int | None = None
    reasoning_effort: Literal["minimal", "low", "medium", "high"] | None = None
    parallel_tool_calls: bool = True
    timeout_s: float | None = None
    metadata: dict[str, str] = field(default_factory=dict)
    # Stable per-tenant/per-surface key improves prompt-cache hit rates.
    cache_key: str | None = None


class LLMError(Exception):
    """Raised for provider failures after retries, or invalid model output."""


class ToolArgumentsError(LLMError):
    """The model produced tool arguments that don't match the tool's schema."""
