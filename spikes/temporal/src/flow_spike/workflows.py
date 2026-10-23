"""Graph interpreter as a Temporal workflow.

Determinism rules this code follows:
- The graph is workflow *input* (the pinned published version), never read from a DB inside the workflow.
- All side effects (DB, LLM, HTTP) happen in activities.
- Waiting for a human is a signal + `wait_condition` with a timeout → a durable timer in history.
- Long executions roll over with continue-as-new, carrying only the cursor and variables.
"""

from dataclasses import dataclass, field
from datetime import timedelta
from typing import Any

from temporalio import activity, workflow
from temporalio.common import RetryPolicy

with workflow.unsafe.imports_passed_through():
    from .graph import FlowGraph


@dataclass
class ActionInput:
    execution_id: str
    node_id: str
    action: str
    vars: dict[str, Any]


@dataclass
class ActionResult:
    output: dict[str, Any]
    outcome: str | None = None


@activity.defn
async def run_action(inp: ActionInput) -> ActionResult:
    # Real implementation dispatches to the node library (agent, http, domain actions…).
    # Large outputs should be stored outside Temporal and returned as a reference.
    activity.logger.info("running %s for node %s", inp.action, inp.node_id)
    return ActionResult(output={"action": inp.action, "ok": True})


@dataclass
class Decision:
    approved: bool
    by: str
    comment: str = ""


@dataclass
class FlowInput:
    graph: FlowGraph
    vars: dict[str, Any] = field(default_factory=dict)
    # Cursor so continue-as-new can resume mid-graph.
    current: str | None = None
    steps_done: int = 0


@dataclass
class NodeRun:
    node_id: str
    outcome: str | None


@dataclass
class FlowResult:
    status: str
    path: list[NodeRun]
    vars: dict[str, Any]


@workflow.defn
class FlowInterpreter:
    def __init__(self) -> None:
        self._decision: Decision | None = None
        self._current: str | None = None
        self._path: list[NodeRun] = []

    @workflow.signal
    def decide(self, decision: Decision) -> None:
        # Only the first decision counts; later ones are ignored (idempotent from the UI's view).
        if self._decision is None:
            self._decision = decision

    @workflow.query
    def current_node(self) -> str | None:
        return self._current

    @workflow.run
    async def run(self, inp: FlowInput) -> FlowResult:
        graph = inp.graph
        vars_ = dict(inp.vars)
        node_id: str | None = inp.current or graph.start
        steps = inp.steps_done

        while node_id is not None:
            if workflow.info().is_continue_as_new_suggested():
                workflow.continue_as_new(
                    FlowInput(graph=graph, vars=vars_, current=node_id, steps_done=steps)
                )

            self._current = node_id
            node = graph.node(node_id)
            outcome = await self._run_node(graph, node.id, node.type, node.params, vars_)
            self._path.append(NodeRun(node.id, outcome))
            steps += 1
            node_id = graph.next_node(node.id, outcome)

        self._current = None
        return FlowResult(status="completed", path=self._path, vars=vars_)

    async def _run_node(
        self,
        graph: FlowGraph,
        node_id: str,
        type_: str,
        params: dict[str, Any],
        vars_: dict[str, Any],
    ) -> str | None:
        if type_ == "action":
            res = await workflow.execute_activity(
                run_action,
                ActionInput(workflow.info().workflow_id, node_id, params["action"], vars_),
                start_to_close_timeout=timedelta(minutes=5),
                retry_policy=RetryPolicy(maximum_attempts=5, backoff_coefficient=2.0),
                summary=f"{graph.flow_id}@v{graph.version}:{node_id}",
            )
            vars_[node_id] = res.output
            return res.outcome

        if type_ == "approval":
            self._decision = None
            try:
                await workflow.wait_condition(
                    lambda: self._decision is not None,
                    timeout=timedelta(hours=params["timeout_hours"]),
                    timeout_summary=f"approval:{node_id}",
                )
            except TimeoutError:
                vars_[node_id] = {"timed_out": True}
                return params.get("on_timeout", "rejected")
            assert self._decision is not None
            vars_[node_id] = {"by": self._decision.by, "comment": self._decision.comment}
            return "approved" if self._decision.approved else "rejected"

        raise ValueError(f"unknown node type {type_!r}")
