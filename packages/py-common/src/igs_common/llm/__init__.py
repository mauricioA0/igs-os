"""Provider-agnostic LLM access. Agents and flow nodes depend on `LLMClient`, not on a vendor."""

from .budget import BudgetedLLM, BudgetExceededError, budget_from_env
from .fake import FakeLLM, Scripted
from .openai_client import OpenAILLM
from .pricing import PriceTable
from .protocol import LLMClient
from .registry import ModelNotConfiguredError, ModelRegistry
from .settings import LLMSettings
from .tools import StepOutcome, ToolHandler, run_tool_loop, run_tool_step
from .types import (
    AssistantTurn,
    Completed,
    ConversationItem,
    GenerateOptions,
    GenerateResult,
    LLMError,
    Message,
    Role,
    StreamEvent,
    TextDelta,
    ToolArgumentsError,
    ToolCall,
    ToolCallReady,
    ToolCallStarted,
    ToolResult,
    ToolSpec,
    Usage,
)


def create_llm(settings: LLMSettings | None = None) -> LLMClient:
    """The configured provider. Only OpenAI today; the protocol keeps the door open.

    With ``IGS_LLM_DAILY_BUDGET_USD`` or ``IGS_LLM_MAX_OUTPUT_TOKENS`` set, calls go through
    `BudgetedLLM` (deployment-wide daily cap, default output ceiling).
    """
    llm: LLMClient = OpenAILLM(settings or LLMSettings())
    daily_budget_usd, max_output_tokens = budget_from_env()
    if daily_budget_usd is None and max_output_tokens is None:
        return llm
    return BudgetedLLM(llm, daily_budget_usd=daily_budget_usd, max_output_tokens=max_output_tokens)


__all__ = [
    "AssistantTurn",
    "BudgetExceededError",
    "BudgetedLLM",
    "Completed",
    "ConversationItem",
    "FakeLLM",
    "GenerateOptions",
    "GenerateResult",
    "LLMClient",
    "LLMError",
    "LLMSettings",
    "Message",
    "ModelNotConfiguredError",
    "ModelRegistry",
    "OpenAILLM",
    "PriceTable",
    "Role",
    "Scripted",
    "StepOutcome",
    "StreamEvent",
    "TextDelta",
    "ToolArgumentsError",
    "ToolCall",
    "ToolCallReady",
    "ToolCallStarted",
    "ToolHandler",
    "ToolResult",
    "ToolSpec",
    "Usage",
    "create_llm",
    "run_tool_loop",
    "run_tool_step",
]
