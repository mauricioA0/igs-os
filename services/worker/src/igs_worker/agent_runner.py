"""Runs one ``agent`` node step inside an activity: model call → policy-gated tools → repeat.

An activity can't wait days, so the runner *pauses* by returning an internal port and its
serialized state; the workflow does the durable wait and calls the activity again:

- ``__needs_approval__`` — the model asked for a tool that needs approval (an external tool,
  or one listed in ``approvalRequiredFor``). The workflow raises an approval and resumes the
  runner with the decision; rejected calls go back to the model as tool errors.
- ``__await_user__`` (conversation mode) — the agent said something and waits for the next
  user message; the workflow delivers the text, waits for the ``user_message`` signal and
  resumes with the reply.

Conversation mode ends when the model calls ``complete`` (port ``completed``, output = the
fields required by ``exit.output``) or ``handoff`` (port ``handoff``), or after ``maxTurns``.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, ValidationError
from temporalio import activity

from igs_common.domain.tools import (
    Decision,
    Principal,
    PrincipalKind,
    TriggerKind,
    decide,
    trigger_trust,
)
from igs_common.llm import (
    AssistantTurn,
    ConversationItem,
    GenerateOptions,
    LLMClient,
    Message,
    Role,
    ToolCall,
    ToolResult,
    ToolSpec,
    Usage,
)

from .activities.types import PORT_AWAIT_USER, PORT_NEEDS_APPROVAL, NodeOutcome, NodeTask
from .agent_tools import ToolBinding, ToolContext, ToolRegistry

MAX_TOOL_OUTPUT_CHARS = 20_000


class CompleteArgs(BaseModel):
    model_config = ConfigDict(extra="forbid")
    output: dict[str, Any] = Field(description="Every field the exit schema requires.")


class HandoffArgs(BaseModel):
    model_config = ConfigDict(extra="forbid")
    reason: str


# ── state (de)serialization ─────────────────────────────────────────────────


def dump_item(item: ConversationItem) -> dict[str, Any]:
    if isinstance(item, Message):
        return {"kind": "message", "role": item.role, "content": item.content}
    if isinstance(item, AssistantTurn):
        return {
            "kind": "assistant",
            "text": item.text,
            "tool_calls": [
                {
                    "call_id": c.call_id,
                    "name": c.name,
                    "arguments": c.arguments,
                    "raw_arguments": c.raw_arguments,
                }
                for c in item.tool_calls
            ],
            "provider": item.provider,
            "provider_items": list(item.provider_items),
        }
    return {
        "kind": "tool_result",
        "call_id": item.call_id,
        "output": item.output,
        "is_error": item.is_error,
    }


def load_item(data: dict[str, Any]) -> ConversationItem:
    match data["kind"]:
        case "message":
            return Message(role=data["role"], content=data["content"])
        case "assistant":
            return AssistantTurn(
                text=data["text"],
                tool_calls=tuple(ToolCall(**c) for c in data["tool_calls"]),
                provider=data.get("provider", ""),
                provider_items=tuple(data.get("provider_items", ())),
            )
        case _:
            return ToolResult(data["call_id"], data["output"], data.get("is_error", False))


def _usage_dict(u: Usage) -> dict[str, int]:
    return {
        "inputTokens": u.input_tokens,
        "cachedInputTokens": u.cached_input_tokens,
        "outputTokens": u.output_tokens,
        "reasoningTokens": u.reasoning_tokens,
    }


def _add_usage(acc: dict[str, int], u: Usage) -> dict[str, int]:
    return {k: acc.get(k, 0) + v for k, v in _usage_dict(u).items()}


def _clip(value: Any) -> str:
    text = value if isinstance(value, str) else json.dumps(value, ensure_ascii=False, default=str)
    return text if len(text) <= MAX_TOOL_OUTPUT_CHARS else text[:MAX_TOOL_OUTPUT_CHARS] + "…"


@dataclass
class _Run:
    """Mutable view of the serialized state for one activity attempt."""

    items: list[ConversationItem]
    pending: list[dict[str, Any]]
    tool_log: list[dict[str, Any]]
    usage: dict[str, int]
    steps: int
    turns: int
    seq: int
    cost_usd: float

    @classmethod
    def load(cls, state: dict[str, Any] | None) -> _Run:
        s = state or {}
        return cls(
            items=[load_item(i) for i in s.get("items", [])],
            pending=list(s.get("pending", [])),
            tool_log=list(s.get("toolCalls", [])),
            usage=dict(s.get("usage", {})),
            steps=int(s.get("steps", 0)),
            turns=int(s.get("turns", 0)),
            seq=int(s.get("seq", 0)),
            cost_usd=float(s.get("costUsd", 0.0)),
        )

    def dump(self) -> dict[str, Any]:
        return {
            "items": [dump_item(i) for i in self.items],
            "pending": self.pending,
            "toolCalls": self.tool_log,
            "usage": self.usage,
            "steps": self.steps,
            "turns": self.turns,
            "seq": self.seq,
            "costUsd": self.cost_usd,
        }


@dataclass
class AgentRunner:
    llm: LLMClient
    tools: ToolRegistry

    async def run(self, task: NodeTask) -> NodeOutcome:
        cfg = task.config
        conversation = cfg.get("mode") == "conversation"
        state = task.state or {}
        run = _Run.load(state.get("run"))
        bindings = {b.name: b for b in self.tools.select(cfg.get("tools") or [])}
        specs = [ToolSpec(b.name, b.description, b.input_model) for b in bindings.values()]
        if conversation:
            exit_cfg = cfg.get("exit") or {}
            specs += [
                ToolSpec("complete", _complete_description(exit_cfg), CompleteArgs),
                ToolSpec("handoff", "Hand the conversation to a person. Say why.", HandoffArgs),
            ]

        # Resume after a durable wait.
        if "decision" in state:
            await self._resolve_pending(task, run, bindings, state["decision"])
            if run.pending:
                return self._pause_for_approval(task, run)
        if "userText" in state:
            run.items.append(Message("user", str(state["userText"])))
            run.turns += 1
        elif not task.state:
            if cfg.get("input"):
                run.items.append(Message("user", str(cfg["input"])))
            elif conversation:
                # Nothing to answer yet: wait for the first user message.
                return NodeOutcome(PORT_AWAIT_USER, {"say": None, "state": {"run": run.dump()}})

        max_turns = int((cfg.get("exit") or {}).get("maxTurns") or 20)
        if conversation and run.turns > max_turns:
            return NodeOutcome("handoff", self._output(run, text="", reason="max_turns"))

        instructions = str(cfg.get("instructions") or "")
        handoff_when = (cfg.get("exit") or {}).get("handoffWhen") if conversation else None
        if handoff_when:
            # Authored on the exit; the model only learns it from here.
            instructions += f"\n\nCall `handoff` when: {handoff_when}"
        options = GenerateOptions(
            instructions=instructions,
            reasoning_effort=cfg.get("effort"),
            cache_key=f"{task.flow_id}:{task.node_id}",
            metadata={"execution": task.execution_id, "node": task.node_id},
        )
        role = Role(str((cfg.get("model") or {}).get("role") or "agent"))
        approval_list = set(cfg.get("approvalRequiredFor") or [])
        max_iterations = int(cfg.get("maxIterations") or 12)

        while run.steps < max_iterations:
            activity.heartbeat(f"step {run.steps}")
            result = await self.llm.generate(role, run.items, tools=specs, options=options)
            run.steps += 1
            run.usage = _add_usage(run.usage, result.usage)
            run.cost_usd += float(result.cost_usd or 0)
            if result.finish_reason in ("length", "content_filter", "refusal", "error"):
                raise RuntimeError(f"model stopped: {result.finish_reason}")
            run.items.append(result.turn)
            if not result.tool_calls:
                if conversation:
                    return NodeOutcome(
                        PORT_AWAIT_USER, {"say": result.text, "state": {"run": run.dump()}}
                    )
                return NodeOutcome("next", self._output(run, text=result.text))

            for call in result.tool_calls:
                if call.name == "complete":
                    done = self._complete(run, call, cfg.get("exit") or {})
                    if done is not None:
                        return done
                    continue
                if call.name == "handoff":
                    reason = str(call.arguments.get("reason", ""))
                    run.items.append(ToolResult(call.call_id, "handed off"))
                    return NodeOutcome("handoff", self._output(run, text="", reason=reason))
                binding = bindings.get(call.name)
                if binding is None:
                    run.items.append(ToolResult(call.call_id, f"unknown tool {call.name!r}", True))
                    continue
                verdict = self._verdict(task, binding, call, approval_list)
                if verdict is Decision.DENY:
                    run.items.append(
                        ToolResult(call.call_id, f"{call.name} is not allowed here", True)
                    )
                    self._log(run, call, "denied")
                elif verdict is Decision.REQUIRE_APPROVAL:
                    run.seq += 1
                    run.pending.append(
                        {
                            "call": {
                                "call_id": call.call_id,
                                "name": call.name,
                                "arguments": call.arguments,
                            },
                            "seq": run.seq,
                            "toolClass": binding.policy(call.arguments).tool_class.value,
                        }
                    )
                else:
                    run.items.append(await self._execute(task, run, binding, call))
            if run.pending:
                return self._pause_for_approval(task, run)

        return NodeOutcome(
            "handoff" if conversation else "next",
            self._output(run, text="", reason="max_iterations"),
        )

    # ── policy & execution ──────────────────────────────────────────────────

    def _verdict(
        self, task: NodeTask, binding: ToolBinding, call: ToolCall, approval_list: set[str]
    ) -> Decision:
        try:
            kind = TriggerKind(task.trigger_type)
        except ValueError:
            kind = TriggerKind.MANUAL
        verdict = decide(
            binding.policy(call.arguments), Principal(PrincipalKind.FLOW), trigger_trust(kind)
        )
        if verdict is Decision.ALLOW and call.name in approval_list:
            return Decision.REQUIRE_APPROVAL
        return verdict

    async def _execute(
        self, task: NodeTask, run: _Run, binding: ToolBinding, call: ToolCall
    ) -> ToolResult:
        run.seq += 1
        ctx = ToolContext(task.tenant_id, task.execution_id, task.node_id, task.iteration, run.seq)
        try:
            args = binding.input_model.model_validate(call.arguments)
        except ValidationError as e:
            self._log(run, call, "invalid")
            return ToolResult(call.call_id, f"invalid arguments: {e.errors()}", True)
        try:
            output = await binding.run(args, ctx)
        except Exception as e:  # noqa: BLE001 - the model sees the failure and can recover
            self._log(run, call, "error", str(e))
            return ToolResult(call.call_id, f"{type(e).__name__}: {e}", True)
        self._log(run, call, "ok")
        return ToolResult(call.call_id, _clip(output))

    async def _resolve_pending(
        self,
        task: NodeTask,
        run: _Run,
        bindings: dict[str, ToolBinding],
        decision: dict[str, Any],
    ) -> None:
        if not run.pending:
            return
        entry = run.pending.pop(0)
        call = ToolCall(**entry["call"])
        if decision.get("decision") == "approved" and call.name in bindings:
            result = await self._execute(task, run, bindings[call.name], call)
            run.tool_log[-1]["approvalId"] = decision.get("approvalId")
        else:
            outcome = decision.get("decision", "rejected")
            comment = decision.get("comment") or ""
            result = ToolResult(
                call.call_id, f"{call.name} was {outcome} by ops. {comment}".strip(), True
            )
            self._log(run, call, outcome)
        run.items.append(result)

    def _pause_for_approval(self, task: NodeTask, run: _Run) -> NodeOutcome:
        nxt = run.pending[0]
        return NodeOutcome(
            PORT_NEEDS_APPROVAL,
            {
                "pending": nxt["call"] | {"seq": nxt["seq"], "toolClass": nxt["toolClass"]},
                "state": {"run": run.dump()},
            },
        )

    def _complete(self, run: _Run, call: ToolCall, exit_cfg: dict[str, Any]) -> NodeOutcome | None:
        output = call.arguments.get("output")
        required = (exit_cfg.get("output") or {}).get("required") or []
        missing = [
            k for k in required if not isinstance(output, dict) or output.get(k) in (None, "")
        ]
        if missing:
            # Not done yet: tell the model, which asks the coach for the rest.
            run.items.append(
                ToolResult(call.call_id, f"missing fields: {', '.join(missing)}", True)
            )
            return None
        run.items.append(ToolResult(call.call_id, "completed"))
        # The exit output *is* the node output (``nodes.<id>.output.email``); run metadata
        # (tool calls, usage, cost) rides along under ``_agent``.
        assert isinstance(output, dict)
        meta = self._output(run, text="")
        return NodeOutcome("completed", {**output, "_agent": meta})

    def _log(self, run: _Run, call: ToolCall, status: str, error: str | None = None) -> None:
        entry: dict[str, Any] = {"name": call.name, "arguments": call.arguments, "status": status}
        if error:
            entry["error"] = error
        run.tool_log.append(entry)

    def _output(
        self, run: _Run, *, text: str, data: Any = None, reason: str | None = None
    ) -> dict[str, Any]:
        out: dict[str, Any] = {
            "text": text,
            "toolCalls": run.tool_log,
            "usage": run.usage,
            "costUsd": round(run.cost_usd, 6),
            "steps": run.steps,
            "turns": run.turns,
        }
        if data is None and text:
            data = _maybe_json(text)
        if data is not None:
            out["data"] = data
            if isinstance(data, dict):
                out.update({k: v for k, v in data.items() if k not in out})
        if reason:
            out["reason"] = reason
        return out


def _maybe_json(text: str) -> Any:
    stripped = text.strip()
    if stripped.startswith("```"):
        stripped = stripped.strip("`").removeprefix("json").strip()
    if not stripped.startswith(("{", "[")):
        return None
    try:
        return json.loads(stripped)
    except json.JSONDecodeError:
        return None


def _complete_description(exit_cfg: dict[str, Any]) -> str:
    required = (exit_cfg.get("output") or {}).get("required") or []
    when = exit_cfg.get("description") or "Call when the goal of the conversation is reached."
    fields = f" Required fields: {', '.join(required)}." if required else ""
    return f"{when}{fields} Put them in `output`."
