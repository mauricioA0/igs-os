"""Public coach chat and proposal against the seeded demo tenant (RLS on, Temporal recorded).

Needs `docker compose up -d db` and a migrated database:

    IGS_TEST_X7_DATABASE_URL=postgresql+asyncpg://igs:igs@localhost:5433/igs_test_x7
    uv run alembic -c packages/py-common/alembic.ini -x url=$IGS_TEST_X7_DATABASE_URL upgrade head

Skipped when the database is not reachable.
"""

import json
import os
from collections.abc import AsyncIterator
from typing import Any
from uuid import UUID, uuid4

import httpx
import pytest
from sqlalchemy import text

from igs_common.db import session as shared
from igs_common.db.enums import ExecutionStatus
from igs_common.db.models import Approval, FlowExecution, OutboxEvent
from igs_common.seed import load as seed_load
from igs_core.api.v1 import public_chat
from igs_core.app import create_app
from igs_core.config import Settings
from igs_core.temporal import RecordingGateway

URL = os.environ.get(
    "IGS_TEST_X7_DATABASE_URL", "postgresql+asyncpg://igs:igs@localhost:5433/igs_test_x7"
)
pytestmark = pytest.mark.asyncio(loop_scope="session")


@pytest.fixture(scope="module")
async def env() -> AsyncIterator[dict[str, Any]]:
    engine = shared.configure(URL)
    try:
        async with engine.connect() as conn:
            exists = await conn.scalar(text("select to_regclass('public.outbox_events')"))
    except OSError:
        await shared.dispose()
        pytest.skip("Postgres not reachable")
    if exists is None:
        await shared.dispose()
        pytest.skip("database not migrated")
    async with shared.system_scope() as session:
        await seed_load(session)
    os.environ["IGS_DB_APP_ROLE"] = "igs_app"
    gateway = RecordingGateway()
    app = create_app(
        Settings(environment="test", database_url=URL, demo_tenant_slug="igs", mcp_enabled=False),
        workflows=gateway,
    )
    if not any(getattr(r, "path", "").startswith("/v1/public") for r in app.routes):
        app.include_router(public_chat.router, prefix="/v1")
    transport = httpx.ASGITransport(app=app)
    async with (
        app.router.lifespan_context(app),
        httpx.AsyncClient(transport=transport, base_url="http://t") as client,
    ):
        yield {"client": client, "gateway": gateway, "app": app}
    os.environ.pop("IGS_DB_APP_ROLE", None)


async def test_start_conversation_runs_the_published_inquiry_flow(env: dict[str, Any]) -> None:
    c, gw = env["client"], env["gateway"]
    r = await c.post("/v1/public/chat/conversations", json={"message": "Hi, women's D1 soccer"})
    assert r.status_code == 201, r.text
    body = r.json()
    workflow_id = f"chat-{body['execution_id']}"
    started = gw.started[workflow_id]
    assert started["flow"]["flow_id"] == "inbound-inquiry"
    assert started["trigger"]["conversationId"] == body["conversation_id"]
    assert started["trigger"]["channel"] == "web"
    # The first message reaches the workflow as a user_message signal.
    sent = [s for s in gw.signals if s[0] == workflow_id]
    assert sent and sent[0][1] == "user_message" and sent[0][2]["text"].startswith("Hi")
    assert "AI concierge" in body["ai_disclosure"]
    async with shared.system_scope() as s:
        row = await s.get(FlowExecution, UUID(body["execution_id"]))
    assert row is not None and row.trigger_kind.value == "chat"


async def test_messages_are_stored_signalled_and_replies_stream(env: dict[str, Any]) -> None:
    c, gw = env["client"], env["gateway"]
    conv = (await c.post("/v1/public/chat/conversations", json={})).json()
    r = await c.post(
        f"/v1/public/chat/conversations/{conv['conversation_id']}/messages",
        json={"text": "24 players, March 2027, Buenos Aires"},
    )
    assert r.status_code == 202 and r.json()["delivered"] is True
    assert gw.signals[-1][2]["text"] == "24 players, March 2027, Buenos Aires"

    # The worker's OutboxMessageSink writes replies like this one.
    async with shared.system_scope() as s:
        tenant = await s.scalar(text("select id from tenants where slug = 'igs'"))
        s.add(
            OutboxEvent(
                tenant_id=tenant,
                type="conversation.reply",
                subject_type="execution",
                subject_id=uuid4(),
                payload={
                    "executionId": conv["execution_id"],
                    "nodeId": "greet",
                    "text": "Great! What level is your team?",
                    "options": [{"id": "d1", "label": "NCAA D1"}],
                    "attachments": [],
                },
            )
        )
        execution = await s.get(FlowExecution, UUID(conv["execution_id"]))
        assert execution is not None
        execution.status = ExecutionStatus.SUCCEEDED  # so the stream ends after the replay

    transcript = (
        await c.get(f"/v1/public/chat/conversations/{conv['conversation_id']}/messages")
    ).json()
    roles = [m["role"] for m in transcript["messages"]]
    assert roles == ["user", "assistant"]
    assert transcript["messages"][1]["options"][0]["label"] == "NCAA D1"

    events: list[tuple[str, str]] = []
    async with c.stream(
        "GET", f"/v1/public/chat/conversations/{conv['conversation_id']}/stream"
    ) as stream:
        event = ""
        async for line in stream.aiter_lines():
            if line.startswith("event:"):
                event = line.split(":", 1)[1].strip()
            elif line.startswith("data:"):
                events.append((event, line.split(":", 1)[1].strip()))
    assert events[0][0] == "message"
    assert json.loads(events[0][1])["text"] == "Great! What level is your team?"
    assert events[-1][0] == "end"

    closed = await c.post(
        f"/v1/public/chat/conversations/{conv['conversation_id']}/messages", json={"text": "hi"}
    )
    assert closed.status_code == 409


async def test_unknown_conversation_is_404(env: dict[str, Any]) -> None:
    r = await env["client"].get(f"/v1/public/chat/conversations/{uuid4()}/messages")
    assert r.status_code == 404


async def test_proposal_is_a_package_price_without_cost_lines(env: dict[str, Any]) -> None:
    r = await env["client"].get("/v1/public/proposals/t-2711")
    assert r.status_code == 200, r.text
    p = r.json()
    assert p["ref"] == "t-2711" and p["team"].startswith("Lakeshore")
    assert p["price_per_person_usd"] > 0
    # IGS terms: US$95 enrollment fee, US$500 installments, balance 110 days before departure.
    assert p["enrollment_fee_usd"] == 95 and p["installment_usd"] == 500
    assert p["balance_due"] == "2026-11-16"  # March 6, 2027 - 110 days
    assert len(p["itinerary"]) == p["days"]
    assert p["opponents"] and all(1 <= o["level_score"] <= 10 for o in p["opponents"])
    dumped = json.dumps(p).lower()
    for leak in ("margin", "breakdown", "unit_price", "paid_usd"):
        assert leak not in dumped
    assert (await env["client"].get("/v1/public/proposals/t-0000")).status_code == 404


async def test_reserve_creates_one_pending_enrollment_approval(env: dict[str, Any]) -> None:
    c = env["client"]
    body = {"name": "Dana Whitfield", "email": "dwhitfield@lakeshore.example"}
    first = await c.post("/v1/public/proposals/t-2711/reserve", json=body)
    assert first.status_code == 201, first.text
    again = await c.post("/v1/public/proposals/t-2711/reserve", json=body)
    assert again.json()["approval_id"] == first.json()["approval_id"]
    async with shared.system_scope() as s:
        approval = await s.get(Approval, UUID(first.json()["approval_id"]))
        assert approval is not None
        assert approval.status.value == "pending" and approval.risk_class.value == "external"
        assert approval.proposed_action["action"] == "request_enrollment"
        assert approval.subject_type == "trip"
        audits = await s.scalar(
            text("select count(*) from audit_log where action = 'proposal.reserve_requested'")
        )
    assert audits >= 1
    assert (await c.get("/v1/public/proposals/t-2711")).json()["enrollment_requested"] is True
    bad = await c.post("/v1/public/proposals/t-2711/reserve", json={"name": "X", "email": "nope"})
    assert bad.status_code == 422


async def test_public_surfaces_are_rate_limited(env: dict[str, Any]) -> None:
    c = env["client"]
    env["app"].state.public_rate_limiter = public_chat.RateLimiter()
    codes = [(await c.post("/v1/public/chat/conversations", json={})).status_code for _ in range(6)]
    assert codes[:5] == [201] * 5 and codes[5] == 429


async def test_public_surfaces_do_not_exist_outside_demo_mode() -> None:
    app = create_app(Settings(environment="test", demo_mode=False, mcp_enabled=False))
    if not any(getattr(r, "path", "").startswith("/v1/public") for r in app.routes):
        app.include_router(public_chat.router, prefix="/v1")
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://t") as c:
        r = await c.get("/v1/public/proposals/t-2711")
    assert r.status_code in (404, 503)
