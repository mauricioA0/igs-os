"""FlowExecutionWorkflow — interprets one published flow version, node by node.

Determinism rules (docs/architecture/temporal.md):
- The pinned flow version is workflow *input*; it is never loaded from a database in here.
  Subflows and map children load their version through an activity, so the result is
  recorded in history.
- Pure nodes (set, condition, switch, end) run inline with the shared deterministic CEL
  (``igs_common.flows.cel``); everything with a side effect runs in an activity.
- Time comes from ``workflow.now()``; waits are durable timers; approvals and user replies
  are signals.
- History stays small: big outputs travel by reference and the run continues-as-new after
  ``max_node_runs_per_run`` node runs, carrying only the cursor, vars and latest outputs.

Multi-step nodes: ``agent`` runs as a sequence of activity calls. When its runner pauses
(tool approval, waiting for the user) the workflow does the durable wait and resumes it with
the result; ``capture`` and ``choice`` wait for the ``user_message`` signal directly.
"""

import asyncio
import hashlib
import json
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Any, Literal

from temporalio import workflow
from temporalio.common import RetryPolicy
from temporalio.exceptions import ActivityError, ApplicationError, ChildWorkflowError

with workflow.unsafe.imports_passed_through():
    from igs_common.flows.cel import ExpressionError, evaluate_bool
    from igs_common.flows.cel import render_value as render

    from ..activities.nodes import ACTIVITY_FOR_TYPE
    from ..activities.types import (
        PORT_AWAIT_USER,
        PORT_NEEDS_APPROVAL,
        ApprovalRequest,
        CaptureParse,
        CaptureParsed,
        ChoiceClassify,
        FlowVersionRef,
        MapChildResult,
        NodeOutcome,
        NodeRunRecord,
        NodeTask,
        OutgoingMessage,
        UserMessage,
    )
    from ..durations import parse_duration
    from ..flow_model import FlowVersion, NodeDef

# Error classes that never retry, whatever the node says (flow-engine.md §11).
ALWAYS_NON_RETRYABLE = ["validation", "expression", "not_found", "config"]
RECORD_BATCH = 50
MAX_MAP_ITEMS = 1000
TOOL_APPROVAL_EXPIRY = timedelta(days=2)


@dataclass
class ExecutionInput:
    execution_id: str
    flow: FlowVersion
    trigger: dict[str, Any] = field(default_factory=dict)
    vars: dict[str, Any] = field(default_factory=dict)
    max_node_runs_per_run: int = 2000
    tenant_id: str | None = None
    # Carried across continue-as-new.
    cursor: str | None = None
    nodes: dict[str, dict[str, Any]] = field(default_factory=dict)
    iterations: dict[str, int] = field(default_factory=dict)
    steps: int = 0
    runs: int = 0
    inbox: list[UserMessage] = field(default_factory=list)


@dataclass
class ApprovalDecision:
    node_id: str
    decision: Literal["approved", "rejected"]
    by: str
    comment: str = ""
    form: dict[str, Any] = field(default_factory=dict)


@dataclass
class ExecutionResult:
    status: Literal["completed", "failed", "cancelled"]
    reason: str | None = None
    output: dict[str, Any] = field(default_factory=dict)
    steps: int = 0
    path: list[str] = field(default_factory=list)  # node ids, this run only


@dataclass
class ExecutionState:
    status: str
    current_node: str | None
    waiting_for: str | None  # approval | timer | child | user | None
    steps: int
    runs: int


class NodeError(Exception):
    def __init__(self, cls: str, message: str) -> None:
        super().__init__(message)
        self.cls = cls
        self.message = message


@workflow.defn(name="FlowExecution")
class FlowExecutionWorkflow:
    def __init__(self) -> None:
        self._status = "running"
        self._current: str | None = None
        self._waiting_for: str | None = None
        self._pending_approval: str | None = None
        self._decision: ApprovalDecision | None = None
        self._cancel_requested = False
        self._records: list[NodeRunRecord] = []
        self._steps = 0
        self._runs = 0
        self._inbox: list[UserMessage] = []
        self._msg_seq: dict[str, int] = {}

    # ── signals & queries ───────────────────────────────────────────────────

    @workflow.signal(name="approval_decision")
    def approval_decision(self, decision: ApprovalDecision) -> None:
        # The API already enforces first-writer-wins; this guards replays and stale signals.
        if self._pending_approval == decision.node_id and self._decision is None:
            self._decision = decision

    @workflow.signal(name="user_message")
    def user_message(self, message: UserMessage) -> None:
        # Queued: a reply that arrives while a node is still working is not lost.
        self._inbox.append(message)

    @workflow.signal(name="cancel")
    def cancel(self) -> None:
        self._cancel_requested = True

    @workflow.query(name="state")
    def state(self) -> ExecutionState:
        return ExecutionState(
            self._status, self._current, self._waiting_for, self._steps, self._runs
        )

    # ── interpreter loop ────────────────────────────────────────────────────

    @workflow.run
    async def run(self, inp: ExecutionInput) -> ExecutionResult:
        flow = inp.flow
        self._steps, self._runs = inp.steps, inp.runs
        self._inbox = list(inp.inbox) + self._inbox
        vars_ = dict(inp.vars)
        nodes = {k: dict(v) for k, v in inp.nodes.items()}
        iterations = dict(inp.iterations)
        cursor: str | None = inp.cursor or flow.entry
        runs_this_run = 0
        path: list[str] = []

        while cursor is not None:
            if self._cancel_requested:
                return await self._finish("cancelled", "cancel signal", {}, path)
            if self._steps >= flow.max_steps:
                return await self._finish("failed", "max_steps_exceeded", {}, path)
            if runs_this_run >= inp.max_node_runs_per_run or (
                runs_this_run > 0 and workflow.info().is_continue_as_new_suggested()
            ):
                await self._flush()
                workflow.continue_as_new(
                    ExecutionInput(
                        execution_id=inp.execution_id,
                        flow=flow,
                        trigger=inp.trigger,
                        vars=vars_,
                        max_node_runs_per_run=inp.max_node_runs_per_run,
                        tenant_id=inp.tenant_id,
                        cursor=cursor,
                        nodes=nodes,
                        iterations=iterations,
                        steps=self._steps,
                        runs=self._runs + 1,
                        inbox=self._inbox,
                    )
                )

            node = flow.node(cursor)
            iteration = iterations.get(node.id, 0) + 1
            iterations[node.id] = iteration
            self._current = node.id
            started = workflow.now()

            if node.type == "end":
                scope = self._scope(inp, vars_, nodes)
                status = node.config.get("status", "completed")
                try:
                    output = render(node.config.get("output", {}), scope)
                    reason = render(node.config.get("reason"), scope)
                except ExpressionError as e:
                    output, reason, status = {}, str(e), "failed"
                self._record(inp, node, iteration, "completed", None, started, output=output)
                path.append(node.id)
                self._steps += 1
                return await self._finish(status, reason, output, path)

            try:
                if node.disabled:
                    port, output, ref = "next", None, None
                else:
                    port, output, ref = await self._run_node(
                        inp, flow, node, iteration, vars_, nodes
                    )
                nodes[node.id] = {
                    "output": output if ref is None else {"$ref": ref.uri, "preview": ref.preview}
                }
                self._record(
                    inp, node, iteration, "completed", port, started, output=output, ref=ref
                )
            except NodeError as err:
                error = {"class": err.cls, "message": err.message}
                self._record(inp, node, iteration, "failed", None, started, error=error)
                if node.on_error == "continue":
                    port = node.success_port()
                    nodes[node.id] = {"output": {"error": error}}
                elif node.on_error == "branch":
                    port = "error"
                    nodes[node.id] = {"output": None, "error": error}
                else:
                    path.append(node.id)
                    self._steps += 1
                    return await self._finish("failed", f"{node.id}: {err.message}", {}, path)

            path.append(node.id)
            self._steps += 1
            runs_this_run += 1
            if len(self._records) >= RECORD_BATCH:
                await self._flush()

            nxt = flow.target(node.id, port)
            if nxt is None and port != "next":
                return await self._finish("failed", f"unrouted_port {node.id}.{port}", {}, path)
            cursor = nxt

        return await self._finish("completed", None, {}, path)

    # ── node handlers ───────────────────────────────────────────────────────

    async def _run_node(
        self,
        inp: ExecutionInput,
        flow: FlowVersion,
        node: NodeDef,
        iteration: int,
        vars_: dict[str, Any],
        nodes: dict[str, dict[str, Any]],
    ) -> tuple[str, Any, Any]:
        scope = self._scope(inp, vars_, nodes)
        try:
            match node.type:
                case "set":
                    assigned = render(node.config["assign"], scope)
                    vars_.update(assigned)
                    return "next", assigned, None
                case "condition":
                    value = evaluate_bool(node.config["expression"], scope)
                    return ("true" if value else "false"), {"value": value}, None
                case "switch":
                    for case in node.config["cases"]:
                        if evaluate_bool(case["expression"], scope):
                            return case["id"], {"case": case["id"]}, None
                    return "default", {"case": None}, None
                case "wait":
                    return await self._wait(node, scope)
                case "approval":
                    return await self._approval(inp, node, iteration, scope)
                case "subflow":
                    return await self._subflow(inp, node, iteration, scope)
                case "map":
                    return await self._map(inp, node, iteration, scope)
                case "say":
                    return await self._say(inp, node, iteration, scope)
                case "capture":
                    return await self._capture(inp, node, iteration, scope, vars_)
                case "choice":
                    return await self._choice(inp, node, iteration, scope)
                case "agent":
                    return await self._agent(inp, flow, node, iteration, scope)
                case t if t in ACTIVITY_FOR_TYPE:
                    task = self._task(inp, flow, node, iteration, render(node.config, scope))
                    outcome = await self._exec(flow, node, task)
                    return outcome.port, outcome.output, outcome.output_ref
                case _:
                    raise NodeError("validation", f"node type {node.type!r} not supported")
        except ExpressionError as e:
            raise NodeError("expression", str(e)) from e

    async def _wait(self, node: NodeDef, scope: dict[str, Any]) -> tuple[str, Any, Any]:
        if node.config["mode"] == "duration":
            delay = parse_duration(node.config["duration"])
        else:
            until = render(node.config["until"], scope)
            delay = datetime.fromisoformat(str(until)) - workflow.now()
        if delay > timedelta(0):
            await self._flush()
            self._waiting_for = "timer"
            await workflow.sleep(delay, summary=f"wait:{node.id}")
            self._waiting_for = None
        return "next", {"resumedAt": workflow.now().isoformat()}, None

    async def _approval(
        self, inp: ExecutionInput, node: NodeDef, iteration: int, scope: dict[str, Any]
    ) -> tuple[str, Any, Any]:
        cfg = node.config
        expires_in = parse_duration(cfg["expiresAfter"])
        request = ApprovalRequest(
            execution_id=inp.execution_id,
            node_id=node.id,
            iteration=iteration,
            title=str(render(cfg["title"], scope)),
            description=render(cfg.get("description"), scope),
            assignees=cfg["assignees"],
            expires_at=(workflow.now() + expires_in).isoformat(),
            links=render(cfg.get("links", []), scope),
        )
        decision = await self._request_decision(node, request, expires_in)
        return decision["decision"], decision, None

    async def _request_decision(
        self, node: NodeDef, request: ApprovalRequest, expires_in: timedelta
    ) -> dict[str, Any]:
        """Create the approval, then wait durably for its decision signal (or expiry)."""
        approval_id = await workflow.execute_activity(
            "flow.create_approval",
            request,
            result_type=str,
            start_to_close_timeout=timedelta(seconds=30),
            retry_policy=RetryPolicy(maximum_attempts=10),
        )
        await self._flush()
        self._pending_approval, self._decision = node.id, None
        self._waiting_for = "approval"
        try:
            await workflow.wait_condition(
                lambda: self._decision is not None,
                timeout=expires_in,
                timeout_summary=f"approval:{node.id}",
            )
        except TimeoutError:
            return {"approvalId": approval_id, "decision": "expired"}
        finally:
            self._pending_approval, self._waiting_for = None, None
        d = self._decision
        assert d is not None
        self._decision = None
        return {
            "approvalId": approval_id,
            "decision": d.decision,
            "by": d.by,
            "decidedAt": workflow.now().isoformat(),
            "comment": d.comment,
            "form": d.form,
        }

    async def _load_child(self, flow_id: str, version: Any) -> FlowVersion:
        return await workflow.execute_activity(
            "flow.load_version",
            FlowVersionRef(flow_id, None if version in (None, "published") else int(version)),
            result_type=FlowVersion,
            start_to_close_timeout=timedelta(seconds=30),
            retry_policy=RetryPolicy(maximum_attempts=5, non_retryable_error_types=["not_found"]),
        )

    async def _subflow(
        self, inp: ExecutionInput, node: NodeDef, iteration: int, scope: dict[str, Any]
    ) -> tuple[str, Any, Any]:
        cfg = node.config
        child_flow = await self._load_child(cfg["flow"], cfg.get("version", "published"))
        child_id = f"exec-{inp.execution_id}-{node.id}-{iteration}"
        child_input = ExecutionInput(
            execution_id=child_id.removeprefix("exec-"),
            flow=child_flow,
            trigger={"parent": {"executionId": inp.execution_id, "nodeId": node.id}},
            vars=render(cfg.get("inputs", {}), scope),
            max_node_runs_per_run=inp.max_node_runs_per_run,
            tenant_id=inp.tenant_id,
        )
        if not cfg.get("wait", True):
            await workflow.start_child_workflow(
                FlowExecutionWorkflow.run,
                child_input,
                id=child_id,
                parent_close_policy=workflow.ParentClosePolicy.ABANDON,
            )
            return "next", {"executionId": child_id}, None
        await self._flush()
        self._waiting_for = "child"
        try:
            result: ExecutionResult = await workflow.execute_child_workflow(
                FlowExecutionWorkflow.run,
                child_input,
                id=child_id,
                parent_close_policy=workflow.ParentClosePolicy.TERMINATE,
            )
        except ChildWorkflowError as e:
            raise NodeError("upstream", f"subflow {cfg['flow']} errored: {e}") from e
        finally:
            self._waiting_for = None
        if result.status != "completed":
            raise NodeError("upstream", f"subflow {cfg['flow']} {result.status}: {result.reason}")
        return "next", result.output, None

    async def _map(
        self, inp: ExecutionInput, node: NodeDef, iteration: int, scope: dict[str, Any]
    ) -> tuple[str, Any, Any]:
        """One child execution per item, ``concurrency`` at a time (flow-engine.md §7.3)."""
        cfg = node.config
        items = render(cfg["items"], scope)
        if not isinstance(items, list):
            raise NodeError("validation", "map items must evaluate to a list")
        if len(items) > MAX_MAP_ITEMS:
            raise NodeError("validation", f"map over {len(items)} items (max {MAX_MAP_ITEMS})")
        child_flow = await self._load_child(cfg["flow"], cfg.get("version", "published"))
        base_vars = render(cfg.get("inputs", {}), scope)
        item_var = cfg.get("itemInput") or "item"
        concurrency = int(cfg.get("concurrency") or 5)
        fail_fast = bool(cfg.get("failFast", False))
        results: list[MapChildResult] = []
        await self._flush()
        self._waiting_for = "child"
        try:
            for start in range(0, len(items), concurrency):
                batch = range(start, min(len(items), start + concurrency))
                done = await asyncio.gather(
                    *(
                        self._map_child(
                            inp,
                            node,
                            iteration,
                            child_flow,
                            i,
                            {**base_vars, item_var: items[i], "index": i},
                        )
                        for i in batch
                    )
                )
                results.extend(done)
                failed = [r for r in done if r.status != "completed"]
                if fail_fast and failed:
                    first = failed[0]
                    raise NodeError(
                        "upstream", f"map item {first.index} {first.status}: {first.reason}"
                    )
        finally:
            self._waiting_for = None
        return (
            "next",
            {
                "count": len(items),
                "results": [r.output if r.status == "completed" else None for r in results],
                "errors": [
                    {"index": r.index, "status": r.status, "reason": r.reason}
                    for r in results
                    if r.status != "completed"
                ],
            },
            None,
        )

    async def _map_child(
        self,
        inp: ExecutionInput,
        node: NodeDef,
        iteration: int,
        child_flow: FlowVersion,
        index: int,
        child_vars: dict[str, Any],
    ) -> MapChildResult:
        child_id = f"exec-{inp.execution_id}-{node.id}-{iteration}-{index}"
        try:
            result: ExecutionResult = await workflow.execute_child_workflow(
                FlowExecutionWorkflow.run,
                ExecutionInput(
                    execution_id=child_id.removeprefix("exec-"),
                    flow=child_flow,
                    trigger={"parent": {"executionId": inp.execution_id, "nodeId": node.id}},
                    vars=child_vars,
                    max_node_runs_per_run=inp.max_node_runs_per_run,
                    tenant_id=inp.tenant_id,
                ),
                id=child_id,
                parent_close_policy=workflow.ParentClosePolicy.TERMINATE,
            )
        except ChildWorkflowError as e:
            return MapChildResult(index, "failed", reason=str(e))
        return MapChildResult(index, result.status, result.output, result.reason)

    # ── conversation ────────────────────────────────────────────────────────

    async def _say(
        self, inp: ExecutionInput, node: NodeDef, iteration: int, scope: dict[str, Any]
    ) -> tuple[str, Any, Any]:
        cfg = node.config
        variants = [cfg["text"], *(cfg.get("variants") or [])]
        # Deterministic per execution, so a replay (and the transcript) never changes.
        digest = hashlib.sha256(f"{inp.execution_id}:{node.id}".encode()).hexdigest()
        text = str(render(variants[int(digest, 16) % len(variants)], scope))
        attachments = render(cfg.get("attachments") or [], scope)
        message_id = await self._send(inp, node, iteration, text, attachments=attachments)
        return "next", {"text": text, "messageId": message_id}, None

    async def _capture(
        self,
        inp: ExecutionInput,
        node: NodeDef,
        iteration: int,
        scope: dict[str, Any],
        vars_: dict[str, Any],
    ) -> tuple[str, Any, Any]:
        cfg = node.config
        wait_for = parse_duration(cfg.get("waitFor") or "PT30M")
        if cfg.get("prompt"):
            await self._send(inp, node, iteration, str(render(cfg["prompt"], scope)))
        schema = cfg.get("extract")
        max_attempts = int(cfg.get("maxAttempts") or 2)
        values: dict[str, Any] = {}
        missing: list[str] = []
        text = ""
        for attempt in range(1, max_attempts + 1):
            reply = await self._await_user(wait_for, node)
            if reply is None:
                return "timeout", {"timedOut": True, "partial": values or None}, None
            text = reply
            if not schema:
                vars_[cfg["variable"]] = text
                return "next", {"value": text, "text": text}, None
            parsed: CaptureParsed = await self._call(
                "conversation.parse_capture",
                CaptureParse(text=text, schema=schema, previous=values),
                CaptureParsed,
                limit=timedelta(minutes=2),
            )
            values, missing = parsed.values, parsed.missing
            if not missing:
                break
            if attempt < max_attempts:
                reprompt = (
                    str(render(cfg["reprompt"], scope))
                    if cfg.get("reprompt")
                    else f"Thanks! Could you also tell me: {', '.join(missing)}?"
                )
                await self._send(inp, node, iteration, reprompt)
        vars_[cfg["variable"]] = values
        return "next", {"value": values, "text": text, "missing": missing}, None

    async def _choice(
        self, inp: ExecutionInput, node: NodeDef, iteration: int, scope: dict[str, Any]
    ) -> tuple[str, Any, Any]:
        cfg = node.config
        options = [
            {
                "id": o["id"],
                "label": str(render(o["label"], scope)),
                "synonyms": o.get("synonyms") or [],
            }
            for o in cfg["options"]
        ]
        await self._send(
            inp,
            node,
            iteration,
            str(render(cfg["prompt"], scope)),
            options=[{"id": o["id"], "label": o["label"]} for o in options],
        )
        reply = await self._await_user(parse_duration(cfg.get("waitFor") or "PT30M"), node)
        if reply is None:
            return "timeout", {"timedOut": True}, None
        wanted = reply.strip().casefold()
        for o in options:
            names = {o["id"].casefold(), o["label"].strip().casefold()}
            names |= {s.strip().casefold() for s in o["synonyms"]}
            if wanted in names:
                return o["id"], {"choice": o["id"], "text": reply, "matched": "exact"}, None
        if (cfg.get("freeText") or "classify") == "classify":
            picked = await self._call(
                "conversation.classify_choice",
                ChoiceClassify(
                    text=reply, options=[{"id": o["id"], "label": o["label"]} for o in options]
                ),
                str | None,
                limit=timedelta(minutes=1),
            )
            if picked:
                return picked, {"choice": picked, "text": reply, "matched": "model"}, None
        return "no_match", {"choice": None, "text": reply}, None

    async def _send(
        self,
        inp: ExecutionInput,
        node: NodeDef,
        iteration: int,
        text: str,
        *,
        options: list[dict[str, str]] | None = None,
        attachments: list[dict[str, Any]] | None = None,
    ) -> str:
        key = f"{node.id}:{iteration}"
        seq = self._msg_seq.get(key, 0)
        self._msg_seq[key] = seq + 1
        return await self._call(
            "conversation.send",
            OutgoingMessage(
                execution_id=inp.execution_id,
                node_id=node.id,
                iteration=iteration,
                seq=seq,
                text=text,
                tenant_id=inp.tenant_id,
                options=options or [],
                attachments=attachments or [],
            ),
            str,
            limit=timedelta(seconds=30),
        )

    async def _await_user(self, wait: timedelta, node: NodeDef) -> str | None:
        """Next queued user message, or None when ``wait`` passes with none."""
        if not self._inbox:
            await self._flush()
            self._waiting_for = "user"
            try:
                await workflow.wait_condition(
                    lambda: bool(self._inbox), timeout=wait, timeout_summary=f"user:{node.id}"
                )
            except TimeoutError:
                return None
            finally:
                self._waiting_for = None
        return self._inbox.pop(0).text

    # ── agent ───────────────────────────────────────────────────────────────

    async def _agent(
        self,
        inp: ExecutionInput,
        flow: FlowVersion,
        node: NodeDef,
        iteration: int,
        scope: dict[str, Any],
    ) -> tuple[str, Any, Any]:
        config = render(node.config, scope)
        state: dict[str, Any] | None = None
        while True:
            task = self._task(inp, flow, node, iteration, config, state)
            outcome = await self._exec(flow, node, task)
            if outcome.port == PORT_NEEDS_APPROVAL:
                pending = outcome.output["pending"]
                decision = await self._request_decision(
                    node,
                    ApprovalRequest(
                        execution_id=inp.execution_id,
                        node_id=node.id,
                        iteration=iteration,
                        title=f"{node.name or node.id}: run {pending['name']}",
                        description=json.dumps(pending["arguments"], ensure_ascii=False)[:2000],
                        assignees={"roles": ["ops"]},
                        expires_at=(workflow.now() + TOOL_APPROVAL_EXPIRY).isoformat(),
                        proposed_action={
                            "tool": pending["name"],
                            "arguments": pending["arguments"],
                        },
                        seq=int(pending.get("seq", 0)),
                    ),
                    TOOL_APPROVAL_EXPIRY,
                )
                state = {**outcome.output["state"], "decision": decision}
            elif outcome.port == PORT_AWAIT_USER:
                if outcome.output.get("say"):
                    await self._send(inp, node, iteration, str(outcome.output["say"]))
                reply = await self._await_user(parse_duration(flow.conversation_idle_timeout), node)
                if reply is None:
                    return "handoff", {"reason": "idle_timeout"}, None
                state = {**outcome.output["state"], "userText": reply}
            else:
                return outcome.port, outcome.output, outcome.output_ref

    # ── activities ──────────────────────────────────────────────────────────

    def _task(
        self,
        inp: ExecutionInput,
        flow: FlowVersion,
        node: NodeDef,
        iteration: int,
        config: dict[str, Any],
        state: dict[str, Any] | None = None,
    ) -> NodeTask:
        return NodeTask(
            execution_id=inp.execution_id,
            flow_id=flow.flow_id,
            version=flow.version,
            node_id=node.id,
            node_type=node.type,
            iteration=iteration,
            config=config,
            tenant_id=inp.tenant_id,
            trigger_type=flow.trigger_type,
            state=state,
        )

    async def _exec(self, flow: FlowVersion, node: NodeDef, task: NodeTask) -> NodeOutcome:
        is_agent = node.type == "agent"
        default_timeout = timedelta(minutes=30 if is_agent else 5)
        try:
            return await workflow.execute_activity(
                ACTIVITY_FOR_TYPE[node.type],
                task,
                result_type=NodeOutcome,
                start_to_close_timeout=(
                    parse_duration(node.timeout) if node.timeout else default_timeout
                ),
                heartbeat_timeout=timedelta(minutes=2) if is_agent else None,
                retry_policy=_retry_policy(node),
                summary=f"{flow.flow_id}@v{flow.version}:{node.id}",
            )
        except ActivityError as e:
            raise _node_error(e) from e

    async def _call(self, name: str, arg: Any, result_type: Any, *, limit: timedelta) -> Any:
        try:
            return await workflow.execute_activity(
                name,
                arg,
                result_type=result_type,
                start_to_close_timeout=limit,
                retry_policy=RetryPolicy(
                    maximum_attempts=5, non_retryable_error_types=ALWAYS_NON_RETRYABLE
                ),
            )
        except ActivityError as e:
            raise _node_error(e) from e

    # ── helpers ─────────────────────────────────────────────────────────────

    def _scope(
        self, inp: ExecutionInput, vars_: dict[str, Any], nodes: dict[str, dict[str, Any]]
    ) -> dict[str, Any]:
        return {
            "trigger": inp.trigger,
            "vars": vars_,
            "nodes": nodes,
            "execution": {
                "id": inp.execution_id,
                "flowId": inp.flow.flow_id,
                "version": inp.flow.version,
                "now": workflow.now(),
                "conversationId": inp.trigger.get("conversationId"),
            },
        }

    def _record(
        self,
        inp: ExecutionInput,
        node: NodeDef,
        iteration: int,
        status: str,
        port: str | None,
        started: datetime,
        *,
        output: Any = None,
        ref: Any = None,
        error: dict[str, Any] | None = None,
    ) -> None:
        self._records.append(
            NodeRunRecord(
                execution_id=inp.execution_id,
                node_id=node.id,
                node_type=node.type,
                iteration=iteration,
                status=status,
                port=port,
                started_at=started.isoformat(),
                ended_at=workflow.now().isoformat(),
                output=output if ref is None else None,
                output_ref=ref,
                error=error,
            )
        )

    async def _flush(self) -> None:
        if not self._records:
            return
        batch, self._records = self._records, []
        await workflow.execute_activity(
            "flow.record_node_runs",
            batch,
            start_to_close_timeout=timedelta(seconds=30),
            retry_policy=RetryPolicy(maximum_attempts=20, maximum_interval=timedelta(minutes=1)),
        )

    async def _finish(
        self,
        status: Literal["completed", "failed", "cancelled"],
        reason: str | None,
        output: dict[str, Any],
        path: list[str],
    ) -> ExecutionResult:
        await self._flush()
        self._status, self._current = status, None
        return ExecutionResult(
            status=status, reason=reason, output=output, steps=self._steps, path=path
        )


def _node_error(e: ActivityError) -> NodeError:
    cause = e.cause
    cls = cause.type if isinstance(cause, ApplicationError) and cause.type else "upstream"
    message = cause.message if isinstance(cause, ApplicationError) else str(cause or e)
    return NodeError(cls, message)


def _retry_policy(node: NodeDef) -> RetryPolicy:
    r = node.retry or {}
    return RetryPolicy(
        maximum_attempts=int(r.get("maxAttempts", 3)),
        initial_interval=parse_duration(r.get("initialInterval", "PT1S")),
        backoff_coefficient=float(r.get("backoffCoefficient", 2.0)),
        maximum_interval=parse_duration(r.get("maxInterval", "PT1M")),
        non_retryable_error_types=sorted(
            set(ALWAYS_NON_RETRYABLE) | set(r.get("nonRetryable", []))
        ),
    )
