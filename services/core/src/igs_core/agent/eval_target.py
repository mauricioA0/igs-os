"""`AgentUnderTest` for `python -m evals.run` (see evals/README.md, "Agent targets").

Drives the real agents against `$DATABASE_URL` with the real models (`IGS_LLM_MODELS`):

- `copilot` scenarios → `Copilot.turn` as an ops user, SQL backend, in-memory history. Write-
  external tools become approval rows exactly as in the panel (point it at a throwaway DB, e.g.
  the one `python -m evals.agent.redteam_fixtures` builds).
- `coach_chat` scenarios → the `qualify` agent node of the published `inbound-inquiry` flow,
  run by the worker's `AgentRunner` under a `chat` (untrusted) trigger, as the public chat does.
  Calls that would need approval are recorded as approvals and resumed as rejected.
- `guide` scenarios → the read-only guide agent (`igs_core.guide`) as the anonymous demo visitor.
"""

from __future__ import annotations

import json
import os
import re
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from types import SimpleNamespace
from typing import Any
from uuid import UUID

from igs_common.llm import create_llm
from igs_common.rag import search_knowledge
from igs_core import db
from igs_core.agent.backend import SqlOpsBackend
from igs_core.agent.runtime import Copilot, TurnRequest
from igs_core.agent.store import MemoryConversationStore, MemoryTraceSink
from igs_core.agent.tools import TOOLS_BY_NAME
from igs_core.guide.agent import guide_config
from igs_core.repositories import Principal
from igs_core.repositories.sql import SqlAccounts, SqlTrips

FLOW = Path(__file__).resolve().parents[5] / "packages/flow-schema/examples/inbound-inquiry.json"
DEFAULT_TENANT = "c19de01d-b0cf-53d8-a4bb-28d28402a028"  # seeded `igs` tenant
_CITATION = re.compile(r"\[([A-Za-z0-9][\w.:-]{1,80})\]")


@dataclass
class _Session:
    surface: str
    conversation_id: UUID | None = None
    state: dict[str, Any] | None = None
    closed: str | None = None
    seen_items: int = 0
    approvals: list[str] = field(default_factory=list)


class EvalTarget:
    name = "igs-core"

    def __init__(self) -> None:
        db.open_engine(os.environ["DATABASE_URL"])
        self._tenant = UUID(os.environ.get("EVALS_TENANT_ID", DEFAULT_TENANT))
        self._llm = create_llm()
        self._copilot = Copilot(
            llm=self._llm,
            backend=SqlOpsBackend(
                db.tenant_session,
                SqlTrips(db.tenant_session),
                SqlAccounts(db.tenant_session),
                knowledge=search_knowledge,
            ),
            conversations=MemoryConversationStore(),
            traces=MemoryTraceSink(),
        )
        self._guide = Copilot(
            llm=self._llm,
            backend=SqlOpsBackend(
                db.tenant_session,
                SqlTrips(db.tenant_session),
                SqlAccounts(db.tenant_session),
                knowledge=search_knowledge,
            ),
            conversations=MemoryConversationStore(),
            traces=MemoryTraceSink(),
            model_name="chat",
            config=guide_config(),
        )
        self._sessions: dict[str, _Session] = {}
        self._runner: Any = None
        self._node_config: dict[str, Any] | None = None
        self._interaction_keys: dict[str, str] | None = None

    async def start(self, scenario: Any, trial: int) -> str:
        sid = f"{scenario.id}#{trial}"
        self._sessions[sid] = _Session(surface=scenario.surface)
        return sid

    async def respond(self, session_id: str, message: str) -> Any:
        session = self._sessions[session_id]
        if session.surface == "copilot":
            return await self._copilot_turn(session, message)
        if session.surface == "guide":
            visitor = Principal(
                kind="demo", tenant_id=self._tenant, role="viewer", subject="evals-visitor"
            )
            return await self._copilot_turn(session, message, agent=self._guide, who=visitor)
        return await self._coach_turn(session, session_id, message)

    # ── ops copilot ────────────────────────────────────────────────────────

    async def _copilot_turn(
        self,
        session: _Session,
        message: str,
        *,
        agent: Copilot | None = None,
        who: Principal | None = None,
    ) -> Any:
        from evals.agent.harness import AgentReply, ToolInvocation

        principal = who or Principal(
            kind="user", tenant_id=self._tenant, role="ops", subject="evals@igs.example"
        )
        request = TurnRequest(message=message, conversation_id=session.conversation_id)
        text: list[str] = []
        calls: dict[str, dict[str, Any]] = {}
        cost = "0"
        async for ev in (agent or self._copilot).turn(principal, request):
            data = ev.data
            match ev.type:
                case "start":
                    session.conversation_id = UUID(data["conversation_id"])
                case "text":
                    text.append(data["delta"])
                case "tool_start":
                    calls[data["call_id"]] = {"name": data["name"], "args": data["input"]}
                case "tool_end":
                    out = data.get("output")
                    approval = out.get("approval_id") if isinstance(out, dict) else None
                    calls[data["call_id"]]["approval"] = approval
                    calls[data["call_id"]]["error"] = data.get("is_error")
                    calls[data["call_id"]]["output"] = out
                case "done":
                    cost = data.get("cost_usd", "0")
                case "error":
                    text.append(f"(error: {data.get('code')})")
        invocations = []
        for c in calls.values():
            tool = TOOLS_BY_NAME.get(c["name"])
            invocations.append(
                ToolInvocation(
                    name=c["name"],
                    args=c["args"],
                    executed=c.get("approval") is None and not c.get("error"),
                    approval_id=c.get("approval"),
                    tool_class=tool.tool_class.value if tool else None,
                    output=c.get("output"),
                )
            )
        reply = "".join(text)
        return AgentReply(
            text=reply,
            tool_calls=tuple(invocations),
            citations=tuple(self._fixture_key(c) for c in _CITATION.findall(reply)),
            cost_usd=_decimal(cost),
        )

    def _fixture_key(self, citation: str) -> str:
        """`interaction:<uuid>` → the fixture key the scenarios name (`int-lak-03`)."""
        if self._interaction_keys is None:
            from igs_common.seed.load import fixture_id

            fixtures = FLOW.parents[3] / "packages/py-common/fixtures/accounts.yaml"
            keys = re.findall(r"key: (int-[\w-]+)", fixtures.read_text(encoding="utf-8"))
            self._interaction_keys = {str(fixture_id("igs", "interaction", k)): k for k in keys}
        _, _, ident = citation.partition("interaction:")
        return self._interaction_keys.get(ident, citation) if ident else citation

    # ── public coach chat ──────────────────────────────────────────────────

    def _coach_runner(self) -> tuple[Any, dict[str, Any]]:
        if self._runner is None:
            from igs_worker import agent_runner
            from igs_worker.agent_runner import AgentRunner
            from igs_worker.agent_tools import default_registry
            from igs_worker.domain_actions import SqlDomainActions
            from igs_worker.retrieval import RagRetriever

            # Outside a Temporal activity there is nothing to heartbeat to.
            agent_runner.activity = SimpleNamespace(heartbeat=lambda *_a, **_k: None)  # type: ignore[assignment]
            self._runner = AgentRunner(
                self._llm, default_registry(SqlDomainActions(), RagRetriever())
            )
            flow = json.loads(FLOW.read_text(encoding="utf-8"))
            node = next(n for n in flow["nodes"] if n["type"] == "agent")
            self._node_config = node["config"]
        assert self._node_config is not None
        return self._runner, self._node_config

    async def _coach_turn(self, session: _Session, session_id: str, message: str) -> Any:
        from evals.agent.harness import AgentReply, ToolInvocation
        from igs_worker.activities.types import PORT_AWAIT_USER, PORT_NEEDS_APPROVAL, NodeTask

        if session.closed:
            return AgentReply(text=f"(conversation ended: {session.closed})")
        runner, config = self._coach_runner()
        execution_id = str(uuid.uuid5(uuid.NAMESPACE_URL, f"evals:{session_id}"))
        state: dict[str, Any] = {"userText": message}
        if session.state is not None:
            state["run"] = session.state
        invocations: list[Any] = []
        text = ""
        run_state: dict[str, Any] | None = None
        for _ in range(4):  # approval pauses resumed as rejected, then the agent answers
            task = NodeTask(
                execution_id=execution_id,
                flow_id="inbound-inquiry",
                version=1,
                node_id="qualify",
                node_type="agent",
                iteration=0,
                config=config,
                tenant_id=str(self._tenant),
                trigger_type="chat",
                state=state,
            )
            outcome = await runner.run(task)
            out = outcome.output or {}
            run_state = (out.get("state") or {}).get("run")
            if outcome.port == PORT_NEEDS_APPROVAL:
                pending = out["pending"]
                approval = f"apr-{session_id}-{pending['seq']}"
                invocations.append(
                    ToolInvocation(
                        name=pending["name"],
                        args=pending["arguments"],
                        executed=False,
                        approval_id=approval,
                        tool_class=pending.get("toolClass"),
                    )
                )
                state = {
                    "run": run_state,
                    "decision": {"decision": "rejected", "comment": "(eval: left pending)"},
                }
                continue
            if outcome.port == PORT_AWAIT_USER:
                session.state = run_state
                text = out.get("say") or ""
            else:
                # The flow answers for the agent from here: `tell_handoff` / `tell_in_review`.
                session.closed = outcome.port
                text = self._flow_says(outcome.port)
                if outcome.port == "handoff":
                    # The flow's `handoff_task` node, so the judge sees the promise is kept.
                    invocations.append(
                        ToolInvocation(
                            name="create_ops_task",
                            args={"title": "Coach asked for a person", "by": "flow:handoff_task"},
                            tool_class="write_internal",
                            output={"reason": out.get("reason")},
                        )
                    )
                run_state = None
            break
        items = (run_state or {}).get("items", [])
        results = {i["call_id"]: i for i in items if i["kind"] == "tool_result"}
        for item in items[session.seen_items :]:
            for call in item.get("tool_calls", []) if item["kind"] == "assistant" else []:
                binding = runner.tools.get(call["name"])
                result = results.get(call["call_id"])
                if binding is None or result is None:  # complete/handoff, or an approval above
                    continue
                invocations.append(
                    ToolInvocation(
                        name=call["name"],
                        args=call.get("arguments", {}),
                        executed=not result.get("is_error"),
                        tool_class=binding.tool_class.value,
                        output=result.get("output"),
                    )
                )
        session.seen_items = len(items)
        return AgentReply(
            text=text, tool_calls=tuple(invocations), citations=tuple(_CITATION.findall(text))
        )

    def _flow_says(self, port: str) -> str:
        flow = json.loads(FLOW.read_text(encoding="utf-8"))
        nodes = {n["id"]: n for n in flow["nodes"]}
        edges = {(e["from"], e.get("port")): e["to"] for e in flow.get("edges", [])}
        nxt = edges.get(("qualify", port))
        for _ in range(5):  # first `say` downstream of the port
            node = nodes.get(nxt or "")
            if node is None:
                break
            if node["type"] == "say":
                return str(node["config"].get("text", ""))
            nxt = edges.get((node["id"], None))
        return f"({port})"


def _decimal(value: Any) -> Any:
    from decimal import Decimal

    return Decimal(str(value or 0))


def create() -> EvalTarget:
    return EvalTarget()
