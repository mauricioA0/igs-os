"""The interface every LLM provider implements."""

from __future__ import annotations

from collections.abc import AsyncIterator, Sequence
from typing import Protocol

from pydantic import BaseModel

from .types import ConversationItem, GenerateOptions, GenerateResult, Role, StreamEvent, ToolSpec


class LLMClient(Protocol):
    provider: str

    async def generate[T: BaseModel](
        self,
        role: Role,
        items: Sequence[ConversationItem],
        *,
        output_model: type[T] | None = None,
        tools: Sequence[ToolSpec] = (),
        options: GenerateOptions | None = None,
    ) -> GenerateResult[T]:
        """One model call. With `output_model`, the final text is parsed into `result.parsed`."""
        ...

    def stream(
        self,
        role: Role,
        items: Sequence[ConversationItem],
        *,
        tools: Sequence[ToolSpec] = (),
        options: GenerateOptions | None = None,
    ) -> AsyncIterator[StreamEvent]:
        """One model call, streamed. Always ends with a `Completed` event."""
        ...

    async def list_available_models(self) -> list[str]:
        """Model ids the provider exposes to this key (use to verify settings)."""
        ...
