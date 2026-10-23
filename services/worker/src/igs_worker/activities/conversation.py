"""Conversational side effects: deliver what a node says, parse replies with a model.

Delivery goes through a ``MessageSink``. In production it is the outbox (the chat socket /
WhatsApp / email dispatchers read it), so a retried activity never sends twice: the message id
is derived from execution, node, iteration and sequence.
"""

from __future__ import annotations

import json
import uuid
from dataclasses import dataclass, field
from typing import Any, Protocol

from pydantic import BaseModel, ConfigDict
from sqlalchemy.ext.asyncio import AsyncEngine
from temporalio import activity
from temporalio.exceptions import ApplicationError

from igs_common.db.models import OutboxEvent
from igs_common.db.session import session_scope
from igs_common.llm import GenerateOptions, LLMClient, Message, Role

from .types import CaptureParse, CaptureParsed, ChoiceClassify, OutgoingMessage


def message_id(msg: OutgoingMessage) -> str:
    return str(
        uuid.uuid5(
            uuid.NAMESPACE_URL,
            f"igs:msg:{msg.execution_id}:{msg.node_id}:{msg.iteration}:{msg.seq}",
        )
    )


class MessageSink(Protocol):
    async def send(self, msg: OutgoingMessage) -> str: ...


@dataclass
class InMemoryMessages:
    sent: dict[str, OutgoingMessage] = field(default_factory=dict)

    async def send(self, msg: OutgoingMessage) -> str:
        mid = message_id(msg)
        self.sent.setdefault(mid, msg)  # idempotent on retry
        return mid

    @property
    def texts(self) -> list[str]:
        return [m.text for m in self.sent.values()]


@dataclass
class OutboxMessageSink:
    engine: AsyncEngine | None = None

    async def send(self, msg: OutgoingMessage) -> str:
        if msg.tenant_id is None:
            raise ApplicationError("message without tenant", type="validation", non_retryable=True)
        mid = message_id(msg)
        async with session_scope(msg.tenant_id, engine=self.engine) as session:
            if await session.get(OutboxEvent, uuid.UUID(mid)) is None:
                session.add(
                    OutboxEvent(
                        id=uuid.UUID(mid),
                        tenant_id=uuid.UUID(msg.tenant_id),
                        type="conversation.reply",
                        subject_type="execution",
                        subject_id=uuid.uuid5(
                            uuid.NAMESPACE_URL, f"igs:execution:{msg.execution_id}"
                        ),
                        payload={
                            "executionId": msg.execution_id,
                            "nodeId": msg.node_id,
                            "channel": msg.channel,
                            "text": msg.text,
                            "options": msg.options,
                            "attachments": msg.attachments,
                        },
                    )
                )
        return mid


class _Pick(BaseModel):
    model_config = ConfigDict(extra="forbid")
    option: str  # option id, or "none"


@dataclass
class ConversationActivities:
    messages: MessageSink = field(default_factory=InMemoryMessages)
    llm: LLMClient | None = None

    @activity.defn(name="conversation.send")
    async def send(self, msg: OutgoingMessage) -> str:
        return await self.messages.send(msg)

    @activity.defn(name="conversation.parse_capture")
    async def parse_capture(self, req: CaptureParse) -> CaptureParsed:
        llm = self._llm()
        schema = req.schema
        instructions = (
            "Extract the fields described by this JSON Schema from the user's reply. Return one "
            "JSON object with only those fields; use null for anything the reply doesn't say. "
            f"Schema: {json.dumps(schema, ensure_ascii=False)}"
        )
        if req.instructions:
            instructions += f"\n{req.instructions}"
        context = (
            f"Already known: {json.dumps(req.previous, ensure_ascii=False)}\n"
            if req.previous
            else ""
        )
        result = await llm.generate(
            Role.FAST,
            [Message("user", f"{context}Reply: {req.text}")],
            options=GenerateOptions(instructions=instructions),
        )
        values = {
            **req.previous,
            **{k: v for k, v in _json_object(result.text).items() if v is not None},
        }
        required = schema.get("required") or []
        return CaptureParsed(
            values=values, missing=[k for k in required if values.get(k) in (None, "")]
        )

    @activity.defn(name="conversation.classify_choice")
    async def classify_choice(self, req: ChoiceClassify) -> str | None:
        llm = self._llm()
        listing = "\n".join(f"- {o['id']}: {o.get('label', '')}" for o in req.options)
        result = await llm.generate(
            Role.FAST,
            [Message("user", req.text)],
            output_model=_Pick,
            options=GenerateOptions(
                instructions=(
                    "Map the user's reply to one of these options and return its id, or 'none' "
                    f"if it matches none of them:\n{listing}"
                )
            ),
        )
        pick = result.parsed.option if result.parsed else "none"
        ids = {o["id"] for o in req.options}
        return pick if pick in ids else None

    def _llm(self) -> LLMClient:
        if self.llm is None:
            raise ApplicationError("no LLM configured", type="config", non_retryable=True)
        return self.llm

    def all(self) -> list[Any]:
        return [self.send, self.parse_capture, self.classify_choice]


def _json_object(text: str) -> dict[str, Any]:
    stripped = text.strip()
    if stripped.startswith("```"):
        stripped = stripped.strip("`").removeprefix("json").strip()
    try:
        value = json.loads(stripped)
    except json.JSONDecodeError as e:
        raise ApplicationError(f"model did not return JSON: {e}", type="upstream") from e
    if not isinstance(value, dict):
        raise ApplicationError("model did not return a JSON object", type="upstream")
    return value
