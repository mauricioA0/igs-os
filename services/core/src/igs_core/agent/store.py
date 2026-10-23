"""Conversation history and run tracing for the copilot.

History is append-only: earlier items are never edited, so provider reasoning state replayed
from `AssistantTurn.provider_items` stays valid. Traces go to agent_runs / agent_steps, the
tables the ops panel's trace viewer reads.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import UTC, datetime
from decimal import Decimal
from typing import Any, Protocol
from uuid import UUID

from sqlalchemy import text

from igs_common.db import uuid7
from igs_common.llm.types import (
    AssistantTurn,
    ConversationItem,
    Message,
    ToolCall,
    ToolResult,
    Usage,
)
from igs_core.repositories.sql import SessionFactory

# ── (De)serialization of conversation items ────────────────────────────────


def item_to_json(item: ConversationItem) -> tuple[str, dict[str, Any]]:
    """Returns (messages.role, content). The table only knows user/assistant roles."""
    match item:
        case Message(role="assistant"):
            return "assistant", {"type": "message", "role": "assistant", "content": item.content}
        case Message():
            return "user", {"type": "message", "role": item.role, "content": item.content}
        case AssistantTurn():
            return "assistant", {
                "type": "assistant_turn",
                "text": item.text,
                "provider": item.provider,
                "provider_items": list(item.provider_items),
                "tool_calls": [
                    {"call_id": c.call_id, "name": c.name, "arguments": c.arguments}
                    for c in item.tool_calls
                ],
            }
        case ToolResult():
            return "user", {
                "type": "tool_result",
                "call_id": item.call_id,
                "output": item.output,
                "is_error": item.is_error,
            }


def item_from_json(content: dict[str, Any]) -> ConversationItem:
    match content.get("type"):
        case "assistant_turn":
            return AssistantTurn(
                text=content.get("text", ""),
                provider=content.get("provider", ""),
                provider_items=tuple(content.get("provider_items", ())),
                tool_calls=tuple(
                    ToolCall(c["call_id"], c["name"], c.get("arguments", {}))
                    for c in content.get("tool_calls", ())
                ),
            )
        case "tool_result":
            return ToolResult(content["call_id"], content["output"], content.get("is_error", False))
        case _:
            return Message(role=content.get("role", "user"), content=content.get("content", ""))


class ConversationStore(Protocol):
    async def create(self, tenant_id: UUID) -> UUID: ...

    async def load(
        self, tenant_id: UUID, conversation_id: UUID
    ) -> list[ConversationItem] | None: ...

    async def append(
        self, tenant_id: UUID, conversation_id: UUID, items: list[ConversationItem]
    ) -> None: ...


@dataclass
class StepRecord:
    idx: int
    tool: str
    input: Any
    output: Any
    is_error: bool
    duration_ms: int


@dataclass
class RunRecord:
    run_id: UUID
    tenant_id: UUID
    conversation_id: UUID | None
    surface: str
    model: str
    started_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    steps: list[StepRecord] = field(default_factory=list)
    usage: Usage = field(default_factory=Usage)
    cost_usd: Decimal | None = None
    latency_ms: int | None = None
    stop_reason: str | None = None
    error: str | None = None


class TraceSink(Protocol):
    async def save(self, run: RunRecord) -> None: ...


# ── In-memory (tests, local without DB) ────────────────────────────────────


class MemoryConversationStore:
    def __init__(self) -> None:
        self.conversations: dict[tuple[UUID, UUID], list[ConversationItem]] = {}

    async def create(self, tenant_id: UUID) -> UUID:
        cid = uuid7()
        self.conversations[(tenant_id, cid)] = []
        return cid

    async def load(self, tenant_id: UUID, conversation_id: UUID) -> list[ConversationItem] | None:
        items = self.conversations.get((tenant_id, conversation_id))
        return list(items) if items is not None else None

    async def append(
        self, tenant_id: UUID, conversation_id: UUID, items: list[ConversationItem]
    ) -> None:
        self.conversations[(tenant_id, conversation_id)].extend(items)


class MemoryTraceSink:
    def __init__(self) -> None:
        self.runs: list[RunRecord] = []

    async def save(self, run: RunRecord) -> None:
        self.runs.append(run)


# ── SQL ────────────────────────────────────────────────────────────────────


class SqlConversationStore:
    def __init__(self, sessions: SessionFactory, *, channel: str = "web") -> None:
        self._sessions = sessions
        self._channel = channel

    async def create(self, tenant_id: UUID) -> UUID:
        cid = uuid7()
        async with self._sessions(tenant_id) as session:
            await session.execute(
                text(
                    "insert into conversations (id, tenant_id, channel, is_simulation,"
                    " created_at, updated_at)"
                    " values (:id, :tenant_id, cast(:channel as channel), false, now(), now())"
                ),
                {"id": cid, "tenant_id": tenant_id, "channel": self._channel},
            )
        return cid

    async def load(self, tenant_id: UUID, conversation_id: UUID) -> list[ConversationItem] | None:
        async with self._sessions(tenant_id) as session:
            exists = await session.execute(
                text("select 1 from conversations where id = :id and tenant_id = :tenant_id"),
                {"id": conversation_id, "tenant_id": tenant_id},
            )
            if exists.first() is None:
                return None
            rows = await session.execute(
                text(
                    "select content from messages where conversation_id = :id"
                    " and tenant_id = :tenant_id order by created_at, id"
                ),
                {"id": conversation_id, "tenant_id": tenant_id},
            )
            return [item_from_json(r[0]) for r in rows.all()]

    async def append(
        self, tenant_id: UUID, conversation_id: UUID, items: list[ConversationItem]
    ) -> None:
        if not items:
            return
        rows = []
        for item in items:
            role, content = item_to_json(item)
            rows.append(
                {
                    "id": uuid7(),  # time-ordered, so order by id preserves append order
                    "tenant_id": tenant_id,
                    "cid": conversation_id,
                    "role": role,
                    "content": json.dumps(content, default=str),
                }
            )
        async with self._sessions(tenant_id) as session:
            await session.execute(
                text(
                    "insert into messages (id, tenant_id, conversation_id, role, content,"
                    " created_at, updated_at)"
                    " values (:id, :tenant_id, :cid, cast(:role as message_role),"
                    " cast(:content as jsonb), now(), now())"
                ),
                rows,
            )


class SqlTraceSink:
    def __init__(self, sessions: SessionFactory) -> None:
        self._sessions = sessions

    async def save(self, run: RunRecord) -> None:
        async with self._sessions(run.tenant_id) as session:
            await session.execute(
                text(
                    """
                    insert into agent_runs (
                        id, tenant_id, conversation_id, surface, model, started_at, latency_ms,
                        input_tokens, output_tokens, cache_read_tokens, cache_write_tokens,
                        cost_usd, stop_reason, error, created_at, updated_at)
                    values (
                        :id, :tenant_id, :cid, cast(:surface as agent_surface), :model, :started_at,
                        :latency_ms, :input_tokens, :output_tokens, :cache_read, :cache_write,
                        :cost, :stop_reason, :error, now(), now())
                    """
                ),
                {
                    "id": run.run_id,
                    "tenant_id": run.tenant_id,
                    "cid": run.conversation_id,
                    "surface": run.surface,
                    "model": run.model,
                    "started_at": run.started_at,
                    "latency_ms": run.latency_ms,
                    "input_tokens": run.usage.input_tokens,
                    "output_tokens": run.usage.output_tokens,
                    "cache_read": run.usage.cached_input_tokens,
                    "cache_write": run.usage.cache_write_tokens,
                    "cost": run.cost_usd or Decimal(0),
                    "stop_reason": run.stop_reason,
                    "error": run.error,
                },
            )
            if run.steps:
                await session.execute(
                    text(
                        """
                        insert into agent_steps (
                            id, tenant_id, run_id, idx, tool, input, output, is_error,
                            duration_ms, created_at, updated_at)
                        values (
                            :id, :tenant_id, :run_id, :idx, :tool, cast(:input as jsonb),
                            cast(:output as jsonb), :is_error, :duration_ms, now(), now())
                        """
                    ),
                    [
                        {
                            "id": uuid7(),
                            "tenant_id": run.tenant_id,
                            "run_id": run.run_id,
                            "idx": s.idx,
                            "tool": s.tool,
                            "input": json.dumps(s.input, default=str),
                            "output": json.dumps(s.output, default=str),
                            "is_error": s.is_error,
                            "duration_ms": s.duration_ms,
                        }
                        for s in run.steps
                    ],
                )
