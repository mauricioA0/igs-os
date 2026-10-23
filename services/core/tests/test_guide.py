"""The guide agent: read-only tools, route pills, the budget fuse and the SSE endpoint."""

from collections.abc import AsyncIterator
from decimal import Decimal
from uuid import UUID

import httpx
import pytest
from agent_test_support import TENANT, FakeOpsBackend, principal
from core_test_support import DEMO_TENANT

from igs_common.domain.tools import ToolClass
from igs_common.llm import BudgetedLLM, FakeLLM, Scripted
from igs_common.llm.budget import MemorySpendStore
from igs_common.llm.types import Message, Role
from igs_core.agent.runtime import Copilot, TurnRequest
from igs_core.agent.store import MemoryConversationStore, MemoryTraceSink
from igs_core.app import create_app
from igs_core.config import Settings
from igs_core.guide.agent import (
    GUIDE_TOOLS,
    allowed_route,
    guide_config,
    guide_instructions,
)


def make(script: list[Scripted], tenant: UUID = TENANT, llm=None) -> tuple[Copilot, FakeLLM]:
    fake = FakeLLM(script)
    guide = Copilot(
        llm or fake,
        FakeOpsBackend(tenant),
        MemoryConversationStore(),
        MemoryTraceSink(),
        config=guide_config(),
    )
    return guide, fake


async def collect(guide: Copilot, request: TurnRequest, note: str | None = None) -> list:
    return [e async for e in guide.turn(principal("demo", "viewer"), request, note=note)]


def test_guide_tools_are_read_only() -> None:
    assert GUIDE_TOOLS, "the guide needs its tools"
    assert all(t.tool_class is ToolClass.READ for t in GUIDE_TOOLS)
    assert all(t.handler is not None and t.propose is None for t in GUIDE_TOOLS)
    names = {t.name for t in GUIDE_TOOLS}
    assert "suggest_route" in names
    assert not names & {"send_proposal", "request_approval", "update_trip_item", "set_trip_status"}


def test_prompt_rules_language_poc_and_grounding() -> None:
    prompt = guide_instructions()
    assert "visitor's language (Spanish, English or Portuguese)" in prompt
    assert "proof of concept (POC)" in prompt and "fictional" in prompt
    assert "Never invent prices" in prompt
    assert "--- PRODUCT GUIDE ---" in prompt and "/ops/approvals" in prompt


@pytest.mark.parametrize(
    ("path", "ok"),
    [
        ("/", True),
        ("/ops", True),
        ("/ops/approvals?id=1", True),
        ("/chat", True),
        ("/proposal/abc", True),
        ("https://evil.example", False),
        ("//evil.example", False),
        ("/admin", False),
        ("javascript:alert(1)", False),
    ],
)
def test_allowed_route(path: str, ok: bool) -> None:
    assert allowed_route(path) is ok


async def test_turn_streams_route_pill_on_the_chat_model() -> None:
    guide, llm = make(
        [
            Scripted(tool_calls=[("suggest_route", {"path": "/ops/approvals", "label": "Ver"})]),
            Scripted(text="Abrí Aprobaciones: ahí está la propuesta (datos ficticios)."),
        ]
    )
    events = await collect(guide, TurnRequest(message="¿dónde apruebo?"), note="On /ops.")
    types = [e.type for e in events]
    assert types[0] == "start" and types[-1] == "done" and "text" in types
    pill = next(e for e in events if e.type == "tool_end").data
    assert pill["name"] == "suggest_route" and not pill["is_error"]
    assert pill["output"] == {"path": "/ops/approvals", "label": "Ver"}
    first = llm.requests[0]
    assert first.role is Role.CHAT
    assert any(isinstance(i, Message) and i.role == "developer" for i in first.items)
    assert first.options is not None
    assert (first.options.cache_key or "").startswith("guide:")


async def test_unknown_route_comes_back_as_tool_error() -> None:
    guide, _ = make(
        [
            Scripted(tool_calls=[("suggest_route", {"path": "https://x.example", "label": "x"})]),
            Scripted(text="Esa no es una pantalla de IGS OS."),
        ]
    )
    events = await collect(guide, TurnRequest(message="llevame"))
    end = next(e for e in events if e.type == "tool_end").data
    assert end["is_error"]


async def test_write_tools_are_unknown_to_the_guide() -> None:
    guide, _ = make(
        [
            Scripted(tool_calls=[("send_proposal", {"trip_id": str(TENANT)})]),
            Scripted(text="No puedo enviar nada."),
        ]
    )
    events = await collect(guide, TurnRequest(message="mandá la propuesta"))
    end = next(e for e in events if e.type == "tool_end").data
    assert end["is_error"] and end["output"]["error"] == "unknown_tool"
    assert "approval_required" not in [e.type for e in events]


async def test_spent_budget_refuses_with_a_clear_error() -> None:
    store = MemorySpendStore()
    llm = BudgetedLLM(FakeLLM([Scripted(text="never")]), daily_budget_usd=Decimal("1"), store=store)
    await store.add(llm._today(), Decimal("5"))
    guide, _ = make([], llm=llm)
    events = await collect(guide, TurnRequest(message="hola"))
    error = next(e for e in events if e.type == "error").data
    assert error["code"] == "budget_exceeded"
    assert "done" not in [e.type for e in events]


# ── SSE endpoint ───────────────────────────────────────────────────────────


@pytest.fixture
async def guide_client(settings: Settings, repos) -> AsyncIterator[httpx.AsyncClient]:
    guide, _ = make([Scripted(text="Hola, soy la guía.")], tenant=DEMO_TENANT)
    app = create_app(settings, repos=repos)
    app.state.guide = guide
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as c:
        yield c


async def test_sse_endpoint_streams_events(guide_client) -> None:
    async with guide_client.stream(
        "POST", "/v1/guide/turns", json={"message": "¿qué es esto?", "page": "/ops"}
    ) as r:
        assert r.status_code == 200
        assert r.headers["content-type"].startswith("text/event-stream")
        body = "".join([chunk async for chunk in r.aiter_text()])
    names = [line.split(": ", 1)[1] for line in body.splitlines() if line.startswith("event: ")]
    assert names[0] == "start" and names[-1] == "done" and "text" in names


async def test_sse_endpoint_validates_body(guide_client) -> None:
    r = await guide_client.post("/v1/guide/turns", json={"message": ""})
    assert r.status_code == 422
