import uuid
from datetime import timedelta

import pytest
from flow_spike.graph import proposal_approval_flow
from flow_spike.workflows import (
    ActionInput,
    ActionResult,
    Decision,
    FlowInput,
    FlowInterpreter,
)
from temporalio import activity
from temporalio.client import WorkflowHistory
from temporalio.testing import WorkflowEnvironment
from temporalio.worker import Replayer, Worker

TASK_QUEUE = "flows-test"


@pytest.fixture
async def env():
    async with await WorkflowEnvironment.start_time_skipping() as env:
        yield env


def make_worker(env: WorkflowEnvironment, calls: list[str]) -> Worker:
    @activity.defn(name="run_action")
    async def fake_run_action(inp: ActionInput) -> ActionResult:
        calls.append(inp.action)
        return ActionResult(output={"action": inp.action})

    return Worker(
        env.client,
        task_queue=TASK_QUEUE,
        workflows=[FlowInterpreter],
        activities=[fake_run_action],
    )


async def test_approved_path_sends_proposal(env: WorkflowEnvironment):
    calls: list[str] = []
    async with make_worker(env, calls):
        handle = await env.client.start_workflow(
            FlowInterpreter.run,
            FlowInput(graph=proposal_approval_flow(), vars={"lead_id": "L1"}),
            id=f"flow-{uuid.uuid4()}",
            task_queue=TASK_QUEUE,
        )
        # Ops approves 20 hours later (time is skipped, not slept).
        await env.sleep(timedelta(hours=20))
        assert await handle.query(FlowInterpreter.current_node) == "approval"
        await handle.signal(FlowInterpreter.decide, Decision(approved=True, by="ops@igs"))
        result = await handle.result()

    assert calls == ["draft_proposal", "send_proposal"]
    assert [r.node_id for r in result.path] == ["draft", "approval", "send"]
    assert result.vars["approval"]["by"] == "ops@igs"


async def test_no_answer_times_out_after_48h(env: WorkflowEnvironment):
    calls: list[str] = []
    async with make_worker(env, calls):
        result = await env.client.execute_workflow(
            FlowInterpreter.run,
            FlowInput(graph=proposal_approval_flow()),
            id=f"flow-{uuid.uuid4()}",
            task_queue=TASK_QUEUE,
        )

    assert calls == ["draft_proposal"]
    assert result.path[-1].outcome == "rejected"
    assert result.vars["approval"] == {"timed_out": True}


async def test_rejected_ends_without_sending(env: WorkflowEnvironment):
    calls: list[str] = []
    async with make_worker(env, calls):
        handle = await env.client.start_workflow(
            FlowInterpreter.run,
            FlowInput(graph=proposal_approval_flow()),
            id=f"flow-{uuid.uuid4()}",
            task_queue=TASK_QUEUE,
        )
        await handle.signal(FlowInterpreter.decide, Decision(approved=False, by="ops@igs"))
        # A second, conflicting signal must not change the outcome.
        await handle.signal(FlowInterpreter.decide, Decision(approved=True, by="someone-else"))
        result = await handle.result()

    assert calls == ["draft_proposal"]
    assert result.path[-1].outcome == "rejected"


async def test_history_replays_deterministically(env: WorkflowEnvironment):
    """The guard we would run in CI against recorded histories before deploying interpreter changes."""
    calls: list[str] = []
    async with make_worker(env, calls):
        handle = await env.client.start_workflow(
            FlowInterpreter.run,
            FlowInput(graph=proposal_approval_flow()),
            id=f"flow-{uuid.uuid4()}",
            task_queue=TASK_QUEUE,
        )
        await handle.signal(FlowInterpreter.decide, Decision(approved=True, by="ops@igs"))
        await handle.result()
        history: WorkflowHistory = await handle.fetch_history()

    await Replayer(workflows=[FlowInterpreter]).replay_workflow(history)
