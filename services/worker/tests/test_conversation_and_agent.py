"""Conversational nodes, map, and agent nodes (tool policy, approvals, conversation turns)."""

import asyncio
from datetime import timedelta
from typing import Any

from temporalio.client import WorkflowHandle
from temporalio.testing import WorkflowEnvironment

from igs_common.llm import FakeLLM, Message, Scripted, ToolResult
from igs_worker.activities.nodes import NodeActivities
from igs_worker.activities.records import InMemoryApprovals, InMemoryFlowVersions
from igs_worker.activities.types import UserMessage
from igs_worker.agent_runner import AgentRunner
from igs_worker.agent_tools import default_registry
from igs_worker.flow_model import FlowVersion
from igs_worker.retrieval import StaticRetriever
from igs_worker.workflows.flow_execution import ApprovalDecision, FlowExecutionWorkflow

from .conftest import FakeActions, FakeDomain, doc, example
from .test_flow_execution import Harness, flow

CHAT = {"type": "chat"}
TENANT = "00000000-0000-0000-0000-0000000000aa"


async def _say(handle: WorkflowHandle, *texts: str) -> None:
    for i, text in enumerate(texts):
        await handle.signal(FlowExecutionWorkflow.user_message, UserMessage(text, f"m{i}"))


async def _wait_for(handle: WorkflowHandle, waiting_for: str, node: str | None = None) -> None:
    for _ in range(200):
        state = await handle.query(FlowExecutionWorkflow.state)
        if state.waiting_for == waiting_for and (node is None or state.current_node == node):
            return
        await asyncio.sleep(0.02)
    raise AssertionError(f"execution never waited for {waiting_for} at {node}")


def agent_harness(
    env: WorkflowEnvironment,
    llm: FakeLLM,
    actions: FakeActions | None = None,
    fake: FakeDomain | None = None,
) -> tuple[Harness, FakeActions, InMemoryApprovals]:
    actions = actions or FakeActions()
    approvals = InMemoryApprovals()
    nodes = NodeActivities(
        agent=AgentRunner(llm, default_registry(actions, StaticRetriever())),
        retriever=StaticRetriever(),
        llm=llm,
    )
    h = Harness(env, fake, nodes=nodes, llm=llm, tenant_id=TENANT)
    h.records.approvals = approvals
    return h, actions, approvals


# ── say / capture / choice ──────────────────────────────────────────────────


def chat_flow(choice_free_text: str = "no_match") -> FlowVersion:
    return flow(
        [
            {
                "id": "greet",
                "type": "say",
                "config": {
                    "text": "Hi {{ trigger.name }}!",
                    "variants": ["Hello {{ trigger.name }}!"],
                },
            },
            {
                "id": "ask_team",
                "type": "capture",
                "config": {"prompt": "What's your team called?", "variable": "team"},
            },
            {
                "id": "pick",
                "type": "choice",
                "config": {
                    "prompt": "Where would you like to go?",
                    "options": [
                        {"id": "ar", "label": "Argentina", "synonyms": ["Buenos Aires"]},
                        {"id": "br", "label": "Brazil"},
                    ],
                    "freeText": choice_free_text,
                },
            },
            {
                "id": "chosen",
                "type": "end",
                "config": {
                    "output": {"team": "{{ vars.team }}", "dest": "{{ nodes.pick.output.choice }}"}
                },
            },
            {"id": "lost", "type": "end", "config": {"output": {"dest": "none"}}},
        ],
        [
            ("greet", "ask_team"),
            ("ask_team", "pick"),
            ("ask_team", "timeout", "lost"),
            ("pick", "ar", "chosen"),
            ("pick", "br", "chosen"),
            ("pick", "no_match", "lost"),
            ("pick", "timeout", "lost"),
        ],
        trigger=CHAT,
    )


async def test_say_capture_choice_with_queued_replies(env: WorkflowEnvironment) -> None:
    h = Harness(env)
    async with h.worker:
        handle = await h.start(chat_flow(), trigger={"name": "Coach Dana"})
        # Replies sent before the nodes ask are queued, not lost.
        await _say(handle, "Lakeshore Women", "  buenos aires ")
        result = await handle.result()
    assert result.status == "completed", result.reason
    assert result.output == {"team": "Lakeshore Women", "dest": "ar"}
    texts = h.messages.texts
    assert texts[0] in ("Hi Coach Dana!", "Hello Coach Dana!")
    assert texts[1:] == ["What's your team called?", "Where would you like to go?"]
    choice_msg = list(h.messages.sent.values())[2]
    assert [o["id"] for o in choice_msg.options] == ["ar", "br"]


async def test_choice_free_text_goes_through_the_model(env: WorkflowEnvironment) -> None:
    llm = FakeLLM([Scripted(json={"option": "br"})])
    h = Harness(env, llm=llm)
    async with h.worker:
        handle = await h.start(chat_flow("classify"), trigger={"name": "Dana"})
        await _say(handle, "Lakeshore", "somewhere with beaches and samba")
        result = await handle.result()
    assert result.output == {"team": "Lakeshore", "dest": "br"}
    assert llm.requests[0].output_model is not None


async def test_capture_times_out(env: WorkflowEnvironment) -> None:
    h = Harness(env)
    async with h.worker:
        handle = await h.start(chat_flow(), trigger={"name": "Dana"})
        await _wait_for(handle, "user", "ask_team")
        await env.sleep(timedelta(hours=1))
        result = await handle.result()
    assert result.output == {"dest": "none"}
    rec = next(r for r in h.sink.records if r.node_id == "ask_team")
    assert rec.port == "timeout"


async def test_capture_extract_reprompts_for_missing_fields(env: WorkflowEnvironment) -> None:
    llm = FakeLLM(
        [
            Scripted(json={"sport": "soccer", "groupSize": None}),
            Scripted(json={"groupSize": 22}),
        ]
    )
    fv = flow(
        [
            {
                "id": "details",
                "type": "capture",
                "config": {
                    "variable": "info",
                    "extract": {
                        "type": "object",
                        "required": ["sport", "groupSize"],
                        "properties": {
                            "sport": {"type": "string"},
                            "groupSize": {"type": "integer"},
                        },
                    },
                    "maxAttempts": 3,
                },
            },
            {
                "id": "done",
                "type": "end",
                "config": {
                    "output": {
                        "size": "{{ vars.info.groupSize }}",
                        "sport": "{{ vars.info.sport }}",
                    }
                },
            },
        ],
        [("details", "done")],
        trigger=CHAT,
    )
    h = Harness(env, llm=llm)
    async with h.worker:
        handle = await h.start(fv)
        await _say(handle, "women's soccer", "we'll be 22")
        result = await handle.result()
    assert result.status == "completed", result.reason
    assert result.output == {"size": 22, "sport": "soccer"}
    assert h.messages.texts == ["Thanks! Could you also tell me: groupSize?"]


# ── map ─────────────────────────────────────────────────────────────────────


def _child_versions() -> InMemoryFlowVersions:
    versions = InMemoryFlowVersions()
    versions.publish(
        doc(
            [
                {"id": "double", "type": "set", "config": {"assign": {"y": "{{ vars.item * 2 }}"}}},
                {"id": "bad", "type": "condition", "config": {"expression": "vars.item == 3"}},
                {
                    "id": "ok",
                    "type": "end",
                    "config": {"output": {"y": "{{ vars.y }}", "tag": "{{ vars.tag }}"}},
                },
                {"id": "ko", "type": "end", "config": {"status": "failed", "reason": "three"}},
            ],
            [("double", "bad"), ("bad", "false", "ok"), ("bad", "true", "ko")],
            flow_id="per-item",
        ),
        version=2,
    )
    return versions


def _map_flow(fail_fast: bool) -> FlowVersion:
    return flow(
        [
            {
                "id": "each",
                "type": "map",
                "config": {
                    "items": "{{ [1, 2, 3, 4] }}",
                    "flow": "per-item",
                    "inputs": {"tag": "t"},
                    "concurrency": 2,
                    "failFast": fail_fast,
                },
            },
            {"id": "done", "type": "end", "config": {"output": {"r": "{{ nodes.each.output }}"}}},
        ],
        [("each", "done")],
    )


async def test_map_runs_children_in_batches_and_collects_errors(env: WorkflowEnvironment) -> None:
    h = Harness(env, versions=_child_versions())
    async with h.worker:
        result = await (await h.start(_map_flow(fail_fast=False))).result()
    out = result.output["r"]
    assert out["count"] == 4
    assert out["results"] == [
        {"y": 2, "tag": "t"},
        {"y": 4, "tag": "t"},
        None,
        {"y": 8, "tag": "t"},
    ]
    assert [(e["index"], e["status"]) for e in out["errors"]] == [(2, "failed")]

    h2 = Harness(env, versions=_child_versions())
    async with h2.worker:
        result = await (await h2.start(_map_flow(fail_fast=True))).result()
    assert result.status == "failed" and "map item 2 failed" in (result.reason or "")


# ── agent ───────────────────────────────────────────────────────────────────


def _agent_flow(tools: list[str], **extra: Any) -> FlowVersion:
    return flow(
        [
            {
                "id": "helper",
                "type": "agent",
                "config": {
                    "mode": "task",
                    "instructions": "Help ops with {{ vars.topic }}.",
                    "input": "Trip {{ vars.trip }}",
                    "tools": tools,
                    **extra,
                },
            },
            {"id": "done", "type": "end", "config": {"output": {"a": "{{ nodes.helper.output }}"}}},
        ],
        [("helper", "done")],
    )


async def test_agent_task_reads_with_tools_and_returns_json(env: WorkflowEnvironment) -> None:
    llm = FakeLLM(
        [
            Scripted(tool_calls=[("get_trip", {"tripId": "t-1"}), ("bogus", {})]),
            Scripted(text='{"summary": "all good"}'),
        ]
    )
    h, actions, _ = agent_harness(env, llm, FakeActions({"get_trip": {"id": "t-1", "title": "BA"}}))
    async with h.worker:
        result = await (
            await h.start(_agent_flow(["get_trip"]), vars={"topic": "x", "trip": "t-1"})
        ).result()
    out = result.output["a"]
    assert out["data"] == {"summary": "all good"} and out["summary"] == "all good"
    assert [(t["name"], t["status"]) for t in out["toolCalls"]] == [("get_trip", "ok")]
    assert actions.calls[0][0] == "get_trip" and actions.calls[0][2].tenant_id == TENANT
    # The model saw the rendered instructions and the unknown tool came back as an error.
    first = llm.requests[0]
    assert first.options is not None and first.options.instructions == "Help ops with x."
    second_items = llm.requests[1].items
    assert any(getattr(i, "is_error", False) for i in second_items)


async def test_agent_external_tool_waits_for_approval(env: WorkflowEnvironment) -> None:
    llm = FakeLLM(
        [
            Scripted(tool_calls=[("send_proposal", {"tripId": "t-1", "to": "dana@lakeshore.edu"})]),
            Scripted(text="Sent."),
        ]
    )
    h, actions, approvals = agent_harness(env, llm)
    async with h.worker:
        handle = await h.start(_agent_flow(["send_proposal"]), vars={"topic": "x", "trip": "t-1"})
        await _wait_for(handle, "approval", "helper")
        assert actions.calls == []  # nothing external happened before the decision
        await env.sleep(timedelta(hours=3))
        await handle.signal(
            FlowExecutionWorkflow.approval_decision,
            ApprovalDecision("helper", "approved", "ana@igs"),
        )
        result = await handle.result()
    assert result.status == "completed"
    assert [c[0] for c in actions.calls] == ["send_proposal"]
    req = approvals.created[0]
    assert req.proposed_action == {
        "tool": "send_proposal",
        "arguments": {"tripId": "t-1", "to": "dana@lakeshore.edu"},
    }
    calls = result.output["a"]["toolCalls"]
    assert calls[0]["status"] == "ok" and calls[0]["approvalId"].startswith("apr-")


async def test_agent_rejected_tool_goes_back_to_the_model(env: WorkflowEnvironment) -> None:
    llm = FakeLLM(
        [
            Scripted(tool_calls=[("send_proposal", {"tripId": "t-1", "to": "c@x.edu"})]),
            Scripted(text="Understood, I won't send it."),
        ]
    )
    h, actions, _ = agent_harness(env, llm)
    async with h.worker:
        handle = await h.start(_agent_flow(["send_proposal"]), vars={"topic": "x", "trip": "t-1"})
        await _wait_for(handle, "approval", "helper")
        await handle.signal(
            FlowExecutionWorkflow.approval_decision,
            ApprovalDecision("helper", "rejected", "ana@igs", comment="price is wrong"),
        )
        result = await handle.result()
    assert actions.calls == []
    assert result.output["a"]["text"] == "Understood, I won't send it."
    rejection = llm.requests[1].items[-1]
    assert isinstance(rejection, ToolResult)
    assert rejection.is_error and "price is wrong" in rejection.output


async def test_agent_approval_required_for_internal_tool(env: WorkflowEnvironment) -> None:
    llm = FakeLLM(
        [
            Scripted(tool_calls=[("update_trip_item", {"itemId": "i-1", "status": "confirmed"})]),
            Scripted(text="done"),
        ]
    )
    h, actions, approvals = agent_harness(env, llm)
    fv = _agent_flow(["update_trip_item"], approvalRequiredFor=["update_trip_item"])
    async with h.worker:
        handle = await h.start(fv, vars={"topic": "x", "trip": "t-1"})
        await _wait_for(handle, "approval", "helper")
        await handle.signal(
            FlowExecutionWorkflow.approval_decision, ApprovalDecision("helper", "approved", "a")
        )
        await handle.result()
    assert len(approvals.created) == 1 and [c[0] for c in actions.calls] == ["update_trip_item"]


async def test_coach_chat_cannot_reach_external_tools_without_approval(
    env: WorkflowEnvironment,
) -> None:
    """Untrusted (chat) trigger: internal writes that aren't coach-safe also need approval."""
    llm = FakeLLM(
        [
            Scripted(tool_calls=[("swap_opponent", {"itemId": "i", "opponentId": "o"})]),
            Scripted(text="ok"),
        ]
    )
    h, actions, approvals = agent_harness(env, llm)
    fv = FlowVersion.from_json(
        doc(
            [
                {
                    "id": "helper",
                    "type": "agent",
                    "config": {
                        "mode": "task",
                        "instructions": "x",
                        "input": "y",
                        "tools": ["swap_opponent"],
                    },
                },
            ],
            [],
            trigger=CHAT,
        ),
        version=1,
    )
    async with h.worker:
        handle = await h.start(fv)
        await _wait_for(handle, "approval", "helper")
        await handle.signal(
            FlowExecutionWorkflow.approval_decision, ApprovalDecision("helper", "rejected", "a")
        )
        await handle.result()
    assert actions.calls == [] and len(approvals.created) == 1


QUALIFIED = {
    "coachName": "Dana Whitfield",
    "email": "dwhitfield@lakeshore.example",
    "organization": "Lakeshore University",
    "sport": "soccer",
    "gender": "women",
    "ageGroup": "college",
    "levelScore": 7,
    "groupSize": 24,
    "destinationCountry": "Argentina",
    "travelStart": "2027-03-07",
    "durationDays": 10,
}


async def test_inbound_inquiry_example_end_to_end(env: WorkflowEnvironment) -> None:
    llm = FakeLLM(
        [
            Scripted(text="Great! Which dates and how many travellers?"),
            Scripted(
                tool_calls=[
                    (
                        "find_opponents",
                        {
                            "sport": "soccer",
                            "gender": "women",
                            "levelScore": 7,
                            "country": "Argentina",
                        },
                    )
                ]
            ),
            # First try misses a field; the runner tells the model, which then completes.
            Scripted(tool_calls=[("complete", {"output": {**QUALIFIED, "email": None}})]),
            Scripted(tool_calls=[("complete", {"output": QUALIFIED})]),
        ]
    )
    fake = FakeDomain(
        {
            "create_lead": {"id": "lead-1"},
            "draft_trip": {"id": "trip-1"},
            "send_proposal": {"queued": True},
        }
    )
    h, actions, approvals = agent_harness(
        env,
        llm,
        FakeActions({"find_opponents": {"opponents": [{"name": "Deportivo Belgrano"}]}}),
        fake,
    )
    fv = FlowVersion.from_json(example("inbound-inquiry"), version=3)
    async with h.worker:
        handle = await h.start(fv, trigger={"conversationId": "conv-1"})
        await _say(
            handle, "Hi! Women's college soccer, level 7, Argentina", "March 7, 24 people, 10 days"
        )
        await _wait_for(handle, "approval", "ops_review")
        await handle.signal(
            FlowExecutionWorkflow.approval_decision,
            ApprovalDecision("ops_review", "approved", "lucia@igs"),
        )
        result = await handle.result()

    assert result.status == "completed", result.reason
    assert result.output == {"leadId": "lead-1", "tripId": "trip-1"}
    lead_call = next(c for c in fake.calls if c.config.get("action") == "create_lead")
    assert lead_call.config["inputs"]["lead"]["email"] == QUALIFIED["email"]
    assert lead_call.config["inputs"]["conversationId"] == "conv-1"
    send = next(c for c in fake.calls if c.config.get("action") == "send_proposal")
    assert send.config["inputs"] == {"tripId": "trip-1", "to": QUALIFIED["email"], "note": ""}
    assert [c[0] for c in actions.calls] == ["find_opponents"]
    texts = h.messages.texts
    assert "Great! Which dates and how many travellers?" in texts
    assert approvals.created[0].title == "Review proposal for Lakeshore University"
    # The second user message was consumed by the agent's second turn.
    last = llm.requests[1].items[-1]
    assert isinstance(last, Message) and last.content == "March 7, 24 people, 10 days"
