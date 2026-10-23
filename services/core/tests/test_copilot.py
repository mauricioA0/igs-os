"""Copilot turns with a scripted model: events, approvals, history and traces."""

import json
from collections.abc import AsyncIterator
from uuid import UUID

import httpx
import pytest
from agent_test_support import ITEM_ID, TENANT, TRIP_ID, FakeOpsBackend, principal
from core_test_support import DEMO_TENANT

from igs_common.llm import FakeLLM, Scripted
from igs_common.llm.types import AssistantTurn, Message, ToolResult
from igs_core.agent.routes import router as copilot_router
from igs_core.agent.runtime import ContextChip, Copilot, TurnRequest
from igs_core.agent.store import (
    MemoryConversationStore,
    MemoryTraceSink,
    item_from_json,
    item_to_json,
)
from igs_core.app import create_app
from igs_core.config import Settings
from igs_core.repositories.base import Principal


def make(
    script: list[Scripted], tenant: UUID = TENANT
) -> tuple[Copilot, FakeLLM, FakeOpsBackend, MemoryConversationStore, MemoryTraceSink]:
    llm, backend = FakeLLM(script), FakeOpsBackend(tenant)
    store, traces = MemoryConversationStore(), MemoryTraceSink()
    return Copilot(llm, backend, store, traces), llm, backend, store, traces


async def collect(copilot: Copilot, who: Principal, request: TurnRequest) -> list:
    return [e async for e in copilot.turn(who, request)]


async def test_turn_runs_tools_creates_approval_and_traces() -> None:
    copilot, llm, backend, store, traces = make(
        [
            Scripted(
                tool_calls=[
                    ("get_trip", {"trip_id": str(TRIP_ID)}),
                    ("send_proposal", {"trip_id": str(TRIP_ID)}),
                ]
            ),
            Scripted(text="Creé la aprobación para enviar la propuesta."),
        ]
    )
    events = await collect(
        copilot,
        principal("user", "ops"),
        TurnRequest(
            message="Mandale la propuesta a Lakeshore",
            context=[ContextChip(kind="trip", id=str(TRIP_ID), label="IGS-2711")],
        ),
    )
    types = [e.type for e in events]
    assert types[0] == "start" and types[-1] == "done"
    assert types.count("tool_start") == 2 and types.count("tool_end") == 2
    assert "approval_required" in types and "text" in types
    approval = next(e for e in events if e.type == "approval_required").data
    assert approval["payload_hash"].startswith("sha256:")
    assert len(backend.approvals) == 1

    # The second model call saw both tool results, the context note and the user message.
    second = llm.requests[1].items
    assert sum(isinstance(i, ToolResult) for i in second) == 2
    assert any(
        isinstance(i, Message) and i.role == "developer" and "IGS-2711" in i.content for i in second
    )

    done = events[-1].data
    history = await store.load(TENANT, UUID(done["conversation_id"]))
    assert history is not None
    assert [type(i).__name__ for i in history] == [
        "Message",
        "Message",
        "AssistantTurn",
        "ToolResult",
        "ToolResult",
        "AssistantTurn",
    ]
    [run] = traces.runs
    assert run.surface == "copilot" and [s.tool for s in run.steps] == ["get_trip", "send_proposal"]
    assert run.usage.input_tokens == 20 and run.error is None and run.stop_reason == "stop"


async def test_conversation_continues_append_only() -> None:
    copilot, llm, _, store, _ = make([Scripted(text="Hola"), Scripted(text="Dale")])
    first = await collect(copilot, principal(), TurnRequest(message="hola"))
    cid = first[-1].data["conversation_id"]
    before = list(await store.load(TENANT, UUID(cid)) or [])
    await collect(copilot, principal(), TurnRequest(message="seguimos", conversation_id=cid))
    after = await store.load(TENANT, UUID(cid))
    assert after is not None and after[: len(before)] == before  # nothing rewritten
    assert len(llm.requests[1].items) == len(before) + 1


async def test_viewer_cannot_write_through_the_copilot() -> None:
    copilot, _, backend, _, _ = make(
        [
            Scripted(
                tool_calls=[("update_trip_item", {"item_id": str(ITEM_ID), "status": "confirmed"})]
            ),
            Scripted(text="No tengo permisos."),
        ]
    )
    events = await collect(copilot, principal("demo", "viewer"), TurnRequest(message="confirmá"))
    end = next(e for e in events if e.type == "tool_end").data
    assert end["is_error"] and end["output"]["error"] == "not_allowed"
    assert backend.updates == [] and backend.approvals == []


async def test_demo_copilot_proposes_but_never_writes() -> None:
    """Public demo: external actions become approval proposals; nothing is executed."""
    copilot, _, backend, _, _ = make(
        [
            Scripted(tool_calls=[("send_proposal", {"trip_id": str(TRIP_ID)})]),
            Scripted(text="Te dejé la propuesta lista para aprobar."),
        ]
    )
    events = await collect(copilot, principal("demo", "viewer"), TurnRequest(message="enviá"))
    assert "approval_required" in [e.type for e in events]
    assert len(backend.approvals) == 1 and backend.updates == []


async def test_viewer_user_still_cannot_propose() -> None:
    """Only the demo principal gets propose-only; a signed-in viewer stays read-only."""
    copilot, _, backend, _, _ = make(
        [
            Scripted(tool_calls=[("send_proposal", {"trip_id": str(TRIP_ID)})]),
            Scripted(text="No tengo permisos."),
        ]
    )
    events = await collect(copilot, principal("user", "viewer"), TurnRequest(message="enviá"))
    end = next(e for e in events if e.type == "tool_end").data
    assert end["is_error"] and end["output"]["error"] == "not_allowed"
    assert backend.approvals == []


async def test_truncated_tool_call_is_never_run() -> None:
    copilot, _, backend, _, traces = make(
        [
            Scripted(
                tool_calls=[("send_proposal", {"trip_id": str(TRIP_ID)})], finish_reason="length"
            )
        ]
    )
    events = await collect(copilot, principal(), TurnRequest(message="x"))
    assert "tool_start" not in [e.type for e in events]
    assert backend.approvals == [] and traces.runs[0].stop_reason == "length"


async def test_model_failure_is_an_error_event_and_a_trace() -> None:
    copilot, _, _, _, traces = make([])  # script exhausted → LLMError
    events = await collect(copilot, principal(), TurnRequest(message="x"))
    assert events[-1].type == "error" and events[-1].data["code"] == "llm_error"
    assert traces.runs[0].error


async def test_unknown_conversation() -> None:
    copilot, *_ = make([])
    events = await collect(
        copilot,
        principal(),
        TurnRequest(message="x", conversation_id=UUID(int=1)),
    )
    assert [e.type for e in events] == ["error"]


def test_items_roundtrip_through_storage() -> None:
    from igs_common.llm.types import ToolCall

    items = [
        Message("user", "hola"),
        AssistantTurn(
            "", (ToolCall("c1", "get_trip", {"trip_id": "x"}),), "openai", ({"type": "reasoning"},)
        ),
        ToolResult("c1", '{"ok": true}', False),
    ]
    restored = [item_from_json(json.loads(json.dumps(item_to_json(i)[1]))) for i in items]
    assert restored[0] == items[0] and restored[2] == items[2]
    turn = restored[1]
    assert isinstance(turn, AssistantTurn) and turn.tool_calls[0].name == "get_trip"
    assert turn.provider_items == ({"type": "reasoning"},)


# ── SSE endpoint ───────────────────────────────────────────────────────────


@pytest.fixture
async def sse_client(
    settings: Settings, repos
) -> AsyncIterator[tuple[httpx.AsyncClient, FakeOpsBackend]]:
    copilot, _, backend, _, _ = make(
        [Scripted(tool_calls=[("list_trips", {})]), Scripted(text="Hay 1 viaje.")],
        tenant=DEMO_TENANT,  # unauthenticated requests run as the read-only demo tenant
    )
    app = create_app(settings, repos=repos)
    app.include_router(copilot_router)
    app.state.copilot = copilot
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as c:
        yield c, backend


async def test_sse_endpoint_streams_events(sse_client) -> None:
    client, _ = sse_client
    async with client.stream(
        "POST", "/v1/copilot/turns", json={"message": "¿qué viajes hay?"}
    ) as r:
        assert r.status_code == 200
        assert r.headers["content-type"].startswith("text/event-stream")
        body = "".join([chunk async for chunk in r.aiter_text()])
    names = [line.split(": ", 1)[1] for line in body.splitlines() if line.startswith("event: ")]
    assert names[0] == "start" and names[-1] == "done"
    assert names.count("tool_end") == 1 and "text" in names


async def test_sse_endpoint_validates_body(sse_client) -> None:
    client, _ = sse_client
    r = await client.post("/v1/copilot/turns", json={"message": ""})
    assert r.status_code == 422
