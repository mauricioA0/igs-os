import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

from temporalio.exceptions import ApplicationError
from temporalio.testing import WorkflowEnvironment
from temporalio.worker import Worker

from igs_common.llm import FakeLLM
from igs_worker.activities.conversation import ConversationActivities, InMemoryMessages
from igs_worker.activities.nodes import NodeActivities
from igs_worker.activities.outputs import InMemoryOutputStore
from igs_worker.activities.records import InMemoryFlowVersions, InMemorySink, RecordActivities
from igs_worker.flow_model import FlowVersion
from igs_worker.workflows.flow_execution import (
    ApprovalDecision,
    ExecutionInput,
    FlowExecutionWorkflow,
)

from .conftest import FakeDomain, doc, example


def flow(
    nodes: list[dict[str, Any]],
    edges: list[tuple],
    entry: str | None = None,
    flow_id: str = "test-flow",
    settings: dict[str, Any] | None = None,
    trigger: dict[str, Any] | None = None,
) -> FlowVersion:
    return FlowVersion.from_json(
        doc(nodes, edges, entry=entry, flow_id=flow_id, settings=settings, trigger=trigger),
        version=1,
    )


class Harness:
    def __init__(
        self,
        env: WorkflowEnvironment,
        fake: FakeDomain | None = None,
        versions: InMemoryFlowVersions | None = None,
        max_inline: int = 256 * 1024,
        extra: list[Any] | None = None,
        nodes: NodeActivities | None = None,
        llm: FakeLLM | None = None,
        tenant_id: str | None = None,
    ):
        self.env = env
        # One queue per harness: Temporal refuses two workers with the same queue in a process.
        self.queue = f"flows-test-{uuid.uuid4().hex[:8]}"
        self.fake = fake or FakeDomain()
        self.sink = InMemorySink()
        self.store = InMemoryOutputStore()
        self.messages = InMemoryMessages()
        self.tenant_id = tenant_id
        self.records = RecordActivities(sink=self.sink, versions=versions or InMemoryFlowVersions())
        self.nodes = nodes or NodeActivities(store=self.store, max_inline_bytes=max_inline)
        self.conversation = ConversationActivities(messages=self.messages, llm=llm)
        # Real agent/knowledge/extract/classify activities + fake domain actions/io.
        self.worker = Worker(
            env.client,
            task_queue=self.queue,
            workflows=[FlowExecutionWorkflow],
            activities=extra
            or [
                self.nodes.run_agent,
                self.nodes.run_knowledge_search,
                self.nodes.run_extract,
                self.nodes.run_classify,
                *self.fake.all(),
                *self.conversation.all(),
                *self.records.all(),
            ],
        )

    async def start(self, fv: FlowVersion, **kw: Any):
        exec_id = uuid.uuid4().hex[:12]
        kw.setdefault("tenant_id", self.tenant_id)
        return await self.env.client.start_workflow(
            FlowExecutionWorkflow.run,
            ExecutionInput(execution_id=exec_id, flow=fv, **kw),
            id=f"exec-{exec_id}",
            task_queue=self.queue,
        )


APPROVAL = {
    "id": "ops_approval",
    "type": "approval",
    "config": {
        "title": "Send proposal to {{ vars.team }}?",
        "assignees": {"roles": ["ops"]},
        "expiresAfter": "P2D",
    },
}


def approval_flow() -> FlowVersion:
    return flow(
        [
            {
                "id": "draft",
                "type": "action",
                "config": {"action": "draft_trip", "inputs": {"leadId": "{{ vars.lead }}"}},
            },
            APPROVAL,
            {"id": "send", "type": "action", "config": {"action": "send_proposal"}},
            {"id": "sent", "type": "end", "config": {"output": {"sent": True}}},
            {"id": "not_sent", "type": "end", "config": {"reason": "{{ 'not approved' }}"}},
        ],
        [
            ("draft", "ops_approval"),
            ("ops_approval", "approved", "send"),
            ("send", "sent"),
            ("ops_approval", "rejected", "not_sent"),
            ("ops_approval", "expired", "not_sent"),
        ],
    )


async def test_logic_nodes_run_inline(env: WorkflowEnvironment) -> None:
    fv = flow(
        [
            {"id": "init", "type": "set", "config": {"assign": {"n": "{{ 3 }}", "label": "x"}}},
            {"id": "big", "type": "condition", "config": {"expression": "vars.n > 2"}},
            {
                "id": "route",
                "type": "switch",
                "config": {"cases": [{"id": "eq3", "expression": "vars.n == 3"}]},
            },
            {"id": "done", "type": "end", "config": {"output": {"n": "{{ vars.n }}"}}},
        ],
        [("init", "big"), ("big", "true", "route"), ("route", "eq3", "done")],
    )
    h = Harness(env)
    async with h.worker:
        result = await (await h.start(fv)).result()
    assert result.status == "completed"
    assert result.output == {"n": 3}
    assert result.path == ["init", "big", "route", "done"]
    assert [r.port for r in h.sink.records] == ["next", "true", "eq3", None]


async def test_approval_approved_after_20h(env: WorkflowEnvironment) -> None:
    h = Harness(env)
    async with h.worker:
        handle = await h.start(approval_flow(), vars={"lead": "l-501", "team": "Lakeshore"})
        await env.sleep(timedelta(hours=20))
        state = await handle.query(FlowExecutionWorkflow.state)
        assert (state.current_node, state.waiting_for) == ("ops_approval", "approval")
        # A decision for another node is ignored; the real one wins.
        await handle.signal(
            FlowExecutionWorkflow.approval_decision,
            ApprovalDecision("other_node", "rejected", "x@igs"),
        )
        await handle.signal(
            FlowExecutionWorkflow.approval_decision,
            ApprovalDecision("ops_approval", "approved", "ana@igs"),
        )
        await handle.signal(
            FlowExecutionWorkflow.approval_decision,
            ApprovalDecision("ops_approval", "rejected", "late@igs"),
        )
        result = await handle.result()
    assert result.status == "completed" and result.output == {"sent": True}
    assert [c.config["action"] for c in h.fake.calls] == ["draft_trip", "send_proposal"]
    assert h.fake.calls[0].config["inputs"] == {"leadId": "l-501"}
    decided = next(r for r in h.sink.records if r.node_id == "ops_approval")
    assert decided.output["by"] == "ana@igs" and decided.port == "approved"


async def test_approval_expires(env: WorkflowEnvironment) -> None:
    h = Harness(env)
    async with h.worker:
        result = await (await h.start(approval_flow(), vars={"lead": "l", "team": "T"})).result()
    assert result.status == "completed" and result.reason == "not approved"
    assert [c.config["action"] for c in h.fake.calls] == ["draft_trip"]


async def test_pre_departure_example_waits_until_t_minus_30(env: WorkflowEnvironment) -> None:
    start = (datetime.now(UTC) + timedelta(days=45)).date().isoformat()
    fake = FakeDomain(
        {
            "get_trip": {
                "id": "t-2711",
                "status": "confirmed",
                "title": "Lakeshore BA",
                "startDate": start,
            },
            "list_trip_items": {"items": [{"id": "i1", "title": "Bus", "providerName": "Tico"}]},
            "create_ops_task": {"taskId": "task-1"},
            "check_trip_readiness": {"ready": True, "openItems": 0},
        }
    )
    h = Harness(env, fake)
    fv = FlowVersion.from_json(example("pre-departure-check"), version=1)
    async with h.worker:
        handle = await h.start(fv, trigger={"trip": {"id": "t-2711", "startDate": start}})
        result = await handle.result()
    assert result.status == "completed", result.reason
    assert result.output == {"unconfirmed": 1}
    actions = [c.config.get("action", c.node_type) for c in h.fake.calls]
    assert actions == [
        "check_trip_readiness",
        "get_trip",
        "check_trip_readiness",
        "request_provider_confirmations",
        "list_trip_items",
        "create_ops_task",
        "send_message",
    ]
    # notify_ops renders its body with the shared CEL `join` helper.
    notify = next(c for c in h.fake.calls if c.node_type == "send_message")
    assert "Bus" in notify.config["body"]
    assert next(r for r in h.sink.records if r.node_id == "notify_ops").status == "completed"
    escalate = next(c for c in h.fake.calls if c.config.get("action") == "create_ops_task")
    assert escalate.config["inputs"]["items"] == ["i1"]
    assert escalate.config["inputs"]["title"] == "1 unconfirmed items for Lakeshore BA"


async def test_pre_departure_hands_open_documents_to_ops(env: WorkflowEnvironment) -> None:
    start = (datetime.now(UTC) + timedelta(days=45)).date().isoformat()
    readiness = {
        "ready": False,
        "openItems": 4,
        "overdueItems": 2,
        "nextDueOn": "2026-11-05",
        "notReady": [{"name": "Isaac C.", "missing": ["br_evisa"], "overdue": ["br_evisa"]}],
        "summary": "21/22 travelers ready; 4 open items (2 overdue, 2 blockers)",
    }
    fake = FakeDomain(
        {
            "get_trip": {"id": "t-2715", "status": "confirmed", "title": "Riverside Rio"},
            "list_trip_items": {"items": []},
            "check_trip_readiness": readiness,
        }
    )
    h = Harness(env, fake)
    fv = FlowVersion.from_json(example("pre-departure-check"), version=1)
    async with h.worker:
        handle = await h.start(fv, trigger={"trip": {"id": "t-2715", "startDate": start}})
        result = await handle.result()
    assert result.status == "completed", result.reason
    assert result.output == {"unconfirmed": 0}
    actions = [c.config.get("action", c.node_type) for c in h.fake.calls]
    assert actions == [
        "check_trip_readiness",
        "create_ops_task",
        "get_trip",
        "check_trip_readiness",
        "create_ops_task",
        "request_provider_confirmations",
        "list_trip_items",
    ]
    first, second = (c for c in h.fake.calls if c.config.get("action") == "create_ops_task")
    assert first.config["inputs"]["title"] == "Collect travel documents: 4 open"
    assert first.config["inputs"]["priority"] == "high"  # something is overdue
    assert first.config["inputs"]["travelers"] == readiness["notReady"]
    assert second.config["inputs"]["title"] == "4 travel documents still open for Riverside Rio"


async def test_on_error_branch_continue_and_fail(env: WorkflowEnvironment) -> None:
    boom = ApplicationError("provider API down", type="upstream", non_retryable=True)
    fake = FakeDomain({"send_proposal": boom, "draft_trip": boom})
    fv = flow(
        [
            {
                "id": "notify",
                "type": "send_message",
                "onError": "continue",
                "config": {"channel": "ops_inbox", "to": "ops", "body": "hi"},
            },
            {
                "id": "send",
                "type": "action",
                "onError": "branch",
                "retry": {"maxAttempts": 1},
                "config": {"action": "send_proposal"},
            },
            {
                "id": "handled",
                "type": "end",
                "config": {"output": {"err": "{{ nodes.send.error.class }}"}},
            },
        ],
        [("notify", "send"), ("send", "error", "handled")],
    )
    h = Harness(env, FakeDomain({"send_message": boom, "send_proposal": boom}))
    async with h.worker:
        result = await (await h.start(fv)).result()
    assert result.status == "completed" and result.output == {"err": "upstream"}

    failing = flow(
        [
            {
                "id": "draft",
                "type": "action",
                "retry": {"maxAttempts": 1},
                "config": {"action": "draft_trip"},
            }
        ],
        [],
    )
    h2 = Harness(env, fake)
    async with h2.worker:
        result = await (await h2.start(failing)).result()
    assert result.status == "failed" and "provider API down" in (result.reason or "")


async def test_unrouted_port_fails_visibly(env: WorkflowEnvironment) -> None:
    fv = flow(
        [
            {"id": "c", "type": "condition", "config": {"expression": "false"}},
            {"id": "x", "type": "end"},
        ],
        [("c", "true", "x")],
    )
    h = Harness(env)
    async with h.worker:
        result = await (await h.start(fv)).result()
    assert result.status == "failed" and result.reason == "unrouted_port c.false"


async def test_loop_continues_as_new_and_respects_max_steps(env: WorkflowEnvironment) -> None:
    nodes = [
        {"id": "inc", "type": "set", "config": {"assign": {"i": "{{ vars.i + 1 }}"}}},
        {"id": "more", "type": "condition", "config": {"expression": "vars.i < 30"}},
        {"id": "done", "type": "end", "config": {"output": {"i": "{{ vars.i }}"}}},
    ]
    edges = [("inc", "more"), ("more", "true", "inc"), ("more", "false", "done")]
    h = Harness(env)
    async with h.worker:
        handle = await h.start(flow(nodes, edges), vars={"i": 0}, max_node_runs_per_run=10)
        result = await handle.result()
        state = await handle.query(FlowExecutionWorkflow.state)
    assert result.status == "completed" and result.output == {"i": 30}
    assert result.steps == 61 and len(result.path) < 61
    assert state.runs >= 5
    assert len(h.sink.records) == 61

    capped = flow(nodes, edges, settings={"maxSteps": 7})
    h2 = Harness(env)
    async with h2.worker:
        result = await (await h2.start(capped, vars={"i": 0})).result()
    assert result.status == "failed" and result.reason == "max_steps_exceeded"


async def test_subflow_runs_child_with_its_published_version(env: WorkflowEnvironment) -> None:
    versions = InMemoryFlowVersions()
    versions.publish(
        doc(
            [
                {"id": "double", "type": "set", "config": {"assign": {"y": "{{ vars.x * 2 }}"}}},
                {"id": "out", "type": "end", "config": {"output": {"y": "{{ vars.y }}"}}},
            ],
            [("double", "out")],
            flow_id="child",
        ),
        version=4,
    )
    fv = flow(
        [
            {
                "id": "call",
                "type": "subflow",
                "config": {"flow": "child", "inputs": {"x": "{{ 21 }}"}},
            },
            {"id": "done", "type": "end", "config": {"output": {"y": "{{ nodes.call.output.y }}"}}},
        ],
        [("call", "done")],
    )
    h = Harness(env, versions=versions)
    async with h.worker:
        result = await (await h.start(fv)).result()
    assert result.status == "completed" and result.output == {"y": 42}


async def test_large_outputs_travel_by_reference(env: WorkflowEnvironment) -> None:
    fv = flow(
        [
            {
                "id": "ask",
                "type": "knowledge_search",
                "config": {"query": "x", "knowledgeBases": ["kb"]},
            },
            {
                "id": "done",
                "type": "end",
                "config": {"output": {"ref": "{{ nodes.ask.output['$ref'] }}"}},
            },
        ],
        [("ask", "done")],
    )
    store, sink = InMemoryOutputStore(), InMemorySink()
    h = Harness(env, extra=[*_big_knowledge(store), *RecordActivities(sink=sink).all()])
    h.store, h.sink = store, sink
    async with h.worker:
        result = await (await h.start(fv)).result()
    uri = result.output["ref"]
    assert uri.startswith("mem://") and len(h.store.objects[uri]) > 1024
    rec = next(r for r in h.sink.records if r.node_id == "ask")
    assert rec.output is None and rec.output_ref is not None


def _big_knowledge(store: InMemoryOutputStore) -> list[Any]:
    from temporalio import activity

    from igs_worker.activities.outputs import inline_or_store
    from igs_worker.activities.types import NodeOutcome, NodeTask

    @activity.defn(name="node.knowledge_search")
    async def big(task: NodeTask) -> NodeOutcome:
        hits = [{"content": "x" * 200, "docId": str(i)} for i in range(20)]
        out, ref = await inline_or_store(
            store, task.execution_id, task.node_id, task.iteration, {"hits": hits}, 1024
        )
        return NodeOutcome("next", out, ref)

    return [big]
