"""Activities that run node types with side effects.

- ``action``: domain action registry (``DomainActions``), same handlers as the agent tools.
- ``agent``: ``AgentRunner`` (tool loop with per-call policy; may pause for approvals/turns).
- ``knowledge_search``: ``Retriever`` (``igs_common.rag``), tenant from the execution.
- ``extract`` / ``classify``: one structured model call.
- ``send_message`` / ``emit_event``: delivered through the outbox-backed sinks.
- ``http``: not available in v0 (egress allowlist and secrets come with phase 4) — fails with a
  ``validation`` error instead of pretending.

Business failures become ``ApplicationError`` with the flow error class as ``type`` so the
workflow's ``onError`` and retry rules apply (flow-engine.md §11).
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any, Protocol

from pydantic import BaseModel, ConfigDict
from temporalio import activity
from temporalio.exceptions import ApplicationError

from igs_common.llm import GenerateOptions, LLMClient, Message, Role

from ..agent_runner import AgentRunner
from ..domain_actions import ActionContext, ActionError, DomainActions
from ..retrieval import Retriever
from .conversation import InMemoryMessages, MessageSink
from .outputs import InMemoryOutputStore, OutputStore, inline_or_store
from .types import NodeOutcome, NodeTask, OutgoingMessage


class EventSink(Protocol):
    async def emit(
        self, tenant_id: str | None, event: str, payload: dict[str, Any], key: str
    ) -> None: ...


@dataclass
class InMemoryEvents:
    emitted: dict[str, tuple[str, dict[str, Any]]] = field(default_factory=dict)

    async def emit(
        self, tenant_id: str | None, event: str, payload: dict[str, Any], key: str
    ) -> None:
        self.emitted.setdefault(key, (event, payload))


class _Choice(BaseModel):
    model_config = ConfigDict(extra="forbid")
    label: str  # a class id, or "default"


def _missing(name: str) -> ApplicationError:
    return ApplicationError(
        f"{name} is not configured on this worker", type="config", non_retryable=True
    )


@dataclass
class NodeActivities:
    store: OutputStore = field(default_factory=InMemoryOutputStore)
    max_inline_bytes: int = 256 * 1024
    actions: DomainActions | None = None
    agent: AgentRunner | None = None
    retriever: Retriever | None = None
    llm: LLMClient | None = None
    messages: MessageSink = field(default_factory=InMemoryMessages)
    events: EventSink = field(default_factory=InMemoryEvents)

    async def _done(self, task: NodeTask, output: Any, port: str = "next") -> NodeOutcome:
        inline, ref = await inline_or_store(
            self.store,
            task.execution_id,
            task.node_id,
            task.iteration,
            output,
            self.max_inline_bytes,
        )
        return NodeOutcome(port=port, output=inline, output_ref=ref)

    @activity.defn(name="node.action")
    async def run_action(self, task: NodeTask) -> NodeOutcome:
        action = task.config.get("action")
        if not action:
            raise ApplicationError(
                "action node without action", type="validation", non_retryable=True
            )
        if self.actions is None:
            raise _missing("domain actions")
        ctx = ActionContext(task.tenant_id, task.execution_id, task.node_id, task.iteration)
        try:
            output = await self.actions.run(action, dict(task.config.get("inputs") or {}), ctx)
        except ActionError as e:
            retryable = e.cls not in ("validation", "not_found")
            raise ApplicationError(str(e), type=e.cls, non_retryable=not retryable) from e
        return await self._done(task, output)

    @activity.defn(name="node.agent")
    async def run_agent(self, task: NodeTask) -> NodeOutcome:
        if self.agent is None:
            raise _missing("agent runner")
        activity.heartbeat("started")
        outcome = await self.agent.run(task)
        if outcome.port.startswith("__"):
            return outcome  # pause: state must reach the workflow inline
        return await self._done(task, outcome.output, outcome.port)

    @activity.defn(name="node.knowledge_search")
    async def run_knowledge_search(self, task: NodeTask) -> NodeOutcome:
        if self.retriever is None:
            raise _missing("retriever")
        if task.tenant_id is None:
            raise ApplicationError(
                "knowledge search needs a tenant", type="validation", non_retryable=True
            )
        cfg = task.config
        result = await self.retriever.search(
            str(cfg["query"]),
            tenant_id=task.tenant_id,
            knowledge_bases=cfg.get("knowledgeBases") or [],
            filters=cfg.get("filters") or {},
            k=int(cfg.get("topK") or 5),
            rerank=bool(cfg.get("rerank", True)),
        )
        min_score = cfg.get("minScore")
        if min_score is not None:
            result["hits"] = [h for h in result["hits"] if float(h.get("score") or 0) >= min_score]
        return await self._done(task, result)

    @activity.defn(name="node.extract")
    async def run_extract(self, task: NodeTask) -> NodeOutcome:
        llm = self._llm()
        cfg = task.config
        schema = cfg.get("schema") or {}
        instructions = (
            "Extract the data described by this JSON Schema from the input. Return one JSON "
            f"object, null for unknown fields. Schema: {json.dumps(schema, ensure_ascii=False)}"
        )
        if cfg.get("instructions"):
            instructions += f"\n{cfg['instructions']}"
        result = await llm.generate(
            _role(cfg, Role.FAST),
            [Message("user", str(cfg["input"]))],
            options=GenerateOptions(instructions=instructions),
        )
        data = _json_object(result.text)
        missing = [k for k in schema.get("required") or [] if data.get(k) is None]
        if missing:
            raise ApplicationError(f"missing required fields: {', '.join(missing)}", type="output")
        return await self._done(task, data)

    @activity.defn(name="node.classify")
    async def run_classify(self, task: NodeTask) -> NodeOutcome:
        llm = self._llm()
        cfg = task.config
        classes = cfg.get("classes") or []
        listing = "\n".join(f"- {c['id']}: {c['description']}" for c in classes)
        instructions = f"Classify the input into one of these ids, or 'default':\n{listing}"
        if cfg.get("instructions"):
            instructions += f"\n{cfg['instructions']}"
        result = await llm.generate(
            _role(cfg, Role.FAST),
            [Message("user", str(cfg["input"]))],
            output_model=_Choice,
            options=GenerateOptions(instructions=instructions),
        )
        label = result.parsed.label if result.parsed else "default"
        port = label if label in {c["id"] for c in classes} else "default"
        return await self._done(task, {"class": port}, port)

    @activity.defn(name="node.io")
    async def run_io(self, task: NodeTask) -> NodeOutcome:
        cfg = task.config
        key = f"{task.execution_id}:{task.node_id}:{task.iteration}"
        match task.node_type:
            case "send_message":
                mid = await self.messages.send(
                    OutgoingMessage(
                        execution_id=task.execution_id,
                        node_id=task.node_id,
                        iteration=task.iteration,
                        seq=0,
                        text=str(cfg["body"]),
                        channel=str(cfg["channel"]),
                        tenant_id=task.tenant_id,
                        attachments=[{"url": a} for a in cfg.get("attachments") or []],
                    )
                )
                return await self._done(
                    task, {"messageId": mid, "channel": cfg["channel"], "to": cfg["to"]}
                )
            case "emit_event":
                await self.events.emit(
                    task.tenant_id, str(cfg["event"]), dict(cfg.get("payload") or {}), key
                )
                return await self._done(task, {"event": cfg["event"]})
            case "http":
                raise ApplicationError(
                    "http nodes are not enabled in v0", type="validation", non_retryable=True
                )
            case other:
                raise ApplicationError(
                    f"node.io can't run {other!r}", type="validation", non_retryable=True
                )

    def _llm(self) -> LLMClient:
        if self.llm is None:
            raise _missing("LLM")
        return self.llm

    def all(self) -> list[Any]:
        return [
            self.run_action,
            self.run_agent,
            self.run_knowledge_search,
            self.run_extract,
            self.run_classify,
            self.run_io,
        ]


def _role(cfg: dict[str, Any], default: Role) -> Role:
    value = (cfg.get("model") or {}).get("role")
    return Role(value) if value else default


def _json_object(text: str) -> dict[str, Any]:
    stripped = text.strip()
    if stripped.startswith("```"):
        stripped = stripped.strip("`").removeprefix("json").strip()
    try:
        value = json.loads(stripped)
    except json.JSONDecodeError as e:
        raise ApplicationError(f"model did not return JSON: {e}", type="output") from e
    if not isinstance(value, dict):
        raise ApplicationError("model did not return a JSON object", type="output")
    return value


ACTIVITY_FOR_TYPE = {
    "action": "node.action",
    "agent": "node.agent",
    "knowledge_search": "node.knowledge_search",
    "extract": "node.extract",
    "classify": "node.classify",
    "http": "node.io",
    "send_message": "node.io",
    "emit_event": "node.io",
}
