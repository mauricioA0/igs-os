"""Replay saved histories against the current interpreter.

Any change to FlowExecutionWorkflow that would break running executions (non-determinism)
fails here. Histories live in tests/histories/*.json and are committed; regenerate them only
on purpose (``IGS_UPDATE_HISTORIES=1``), e.g. after adding a ``workflow.patched`` branch.
"""

import json
import os
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from temporalio.client import WorkflowHistory
from temporalio.testing import WorkflowEnvironment
from temporalio.worker import Replayer

from igs_common.llm import FakeLLM, Scripted
from igs_worker.flow_model import FlowVersion
from igs_worker.workflows.flow_execution import ApprovalDecision, FlowExecutionWorkflow

from .conftest import FakeActions, FakeDomain, example
from .test_conversation_and_agent import QUALIFIED, _say, _wait_for, agent_harness
from .test_flow_execution import Harness, approval_flow

HISTORIES = Path(__file__).parent / "histories"
UPDATE = os.environ.get("IGS_UPDATE_HISTORIES") == "1"


async def _save(handle, name: str) -> None:
    path = HISTORIES / f"{name}.json"
    if path.exists() and not UPDATE:
        return
    history = await handle.fetch_history()
    path.write_text(json.dumps(json.loads(history.to_json()), indent=1))


async def test_record_histories(env: WorkflowEnvironment) -> None:
    HISTORIES.mkdir(exist_ok=True)
    h = Harness(env)
    async with h.worker:
        handle = await h.start(approval_flow(), vars={"lead": "l-501", "team": "Lakeshore"})
        await env.sleep(timedelta(hours=20))
        await handle.signal(
            FlowExecutionWorkflow.approval_decision,
            ApprovalDecision("ops_approval", "approved", "ana@igs"),
        )
        await handle.result()
        await _save(handle, "approval-approved")

    start = (datetime.now(UTC) + timedelta(days=45)).date().isoformat()
    h2 = Harness(
        env,
        FakeDomain(
            {
                "get_trip": {
                    "id": "t-2711",
                    "status": "confirmed",
                    "title": "Lakeshore BA",
                    "startDate": start,
                },
                "list_trip_items": {"items": []},
                "check_trip_readiness": {"ready": True, "openItems": 0},
            }
        ),
    )
    async with h2.worker:
        handle = await h2.start(
            FlowVersion.from_json(example("pre-departure-check"), version=1),
            trigger={"trip": {"id": "t-2711", "startDate": start}},
        )
        await handle.result()
        await _save(handle, "pre-departure-all-confirmed")

    # Conversational: say → agent turns (tool call, incomplete exit, exit) → approval → send.
    llm = FakeLLM(
        [
            Scripted(text="Great! Which dates?"),
            Scripted(tool_calls=[("find_opponents", {"sport": "soccer", "gender": "women"})]),
            Scripted(tool_calls=[("complete", {"output": QUALIFIED})]),
        ]
    )
    fake = FakeDomain({"create_lead": {"id": "lead-1"}, "draft_trip": {"id": "trip-1"}})
    h3, _, _ = agent_harness(env, llm, FakeActions(), fake)
    async with h3.worker:
        handle = await h3.start(
            FlowVersion.from_json(example("inbound-inquiry"), version=3),
            trigger={"conversationId": "conv-1"},
        )
        await _say(handle, "Women's college soccer", "March 7, 24 people, 10 days")
        await _wait_for(handle, "approval", "ops_review")
        await handle.signal(
            FlowExecutionWorkflow.approval_decision,
            ApprovalDecision("ops_review", "approved", "lucia@igs"),
        )
        await handle.result()
        await _save(handle, "inbound-inquiry-approved")


@pytest.mark.parametrize("path", sorted(HISTORIES.glob("*.json")), ids=lambda p: p.stem)
async def test_replay(path: Path) -> None:
    history = WorkflowHistory.from_json(path.stem, path.read_text())  # noqa: ASYNC240
    await Replayer(workflows=[FlowExecutionWorkflow]).replay_workflow(history)
