"""Trip item updates, leads and the richer trip/account read models against real Postgres.

The database (``igs_test_y4``) is created and migrated by ``conftest.py`` and seeded here with
the demo tenant; writes go through an ops API key, reads also through the public demo.
"""

import os
from collections.abc import AsyncIterator
from typing import Any
from uuid import UUID, uuid4

import httpx
import pytest
from sqlalchemy import select, text

from igs_common.db import session as shared
from igs_common.db.models import AuditLog, OutboxEvent
from igs_common.seed import fixture_id, load
from igs_common.testing import database_url
from igs_core.app import create_app
from igs_core.config import Settings
from igs_core.deps import hash_api_key
from igs_core.repositories.sql import trip_item
from igs_core.temporal import RecordingGateway

URL = database_url("igs_test_y4", driver="postgresql+asyncpg")
TRIP = fixture_id("igs", "trip", "t-2711")
LEAD = fixture_id("igs", "lead", "l-508")
ACCOUNT = fixture_id("igs", "account", "acc-lakeshore")
pytestmark = pytest.mark.asyncio(loop_scope="session")


@pytest.fixture(scope="module")
async def env() -> AsyncIterator[dict[str, Any]]:
    engine = shared.configure(URL)
    try:
        async with shared.system_scope() as session:
            await load(session)
    except OSError:
        await shared.dispose()
        pytest.skip("Postgres not reachable")
    key = f"igs_y4_{uuid4().hex}"
    async with engine.begin() as conn:
        tenant = await conn.scalar(text("select id from tenants where slug = 'igs'"))
        user = uuid4()
        await conn.execute(
            text(
                "insert into users (id, tenant_id, email, name, role) "
                "values (:user, :tenant, :email, 'Ops Y4', 'ops')"
            ),
            {"user": user, "tenant": tenant, "email": f"{user.hex}@y4.test"},
        )
        await conn.execute(
            text(
                "insert into api_keys (id, tenant_id, name, prefix, hash, scopes, created_by) "
                "values (gen_random_uuid(), :tenant, 'ops-y4', 'igs_', :hash, :scopes, :user)"
            ),
            {"tenant": tenant, "hash": hash_api_key(key), "scopes": ["igs:write"], "user": user},
        )
    os.environ["IGS_DB_APP_ROLE"] = "igs_app"
    app = create_app(
        Settings(environment="test", database_url=URL, demo_tenant_slug="igs", mcp_enabled=False),
        workflows=RecordingGateway(),
    )
    transport = httpx.ASGITransport(app=app)
    async with (
        app.router.lifespan_context(app),
        httpx.AsyncClient(transport=transport, base_url="http://t") as client,
    ):
        yield {"client": client, "ops": {"Authorization": f"Bearer {key}"}, "tenant": tenant}
    os.environ.pop("IGS_DB_APP_ROLE", None)


async def test_trip_item_mapping_nests_opponent_and_provider() -> None:
    base = {
        "id": uuid4(),
        "day": 3,
        "slot": "afternoon",
        "kind": "match",
        "title": "vs Club",
        "status": "pending",
        "opponent_name": "Deportivo Belgrano",
        "opponent_level": 7,
        "provider_name": None,
        "provider_kind": None,
    }
    item = trip_item(base)
    assert item.opponent is not None and item.opponent.level_score == 7
    assert item.provider is None


async def _first_item(c: httpx.AsyncClient, status: str) -> dict[str, Any]:
    trip = (await c.get(f"/v1/trips/{TRIP}")).json()
    return next(i for i in trip["items"] if i["status"] == status)


async def test_trip_items_are_richer(env: dict[str, Any]) -> None:
    trip = (await env["client"].get(f"/v1/trips/{TRIP}")).json()
    assert trip["items"], trip
    keys = set(trip["items"][0])
    assert {"time", "alert", "opponent", "provider"} <= keys
    assert any(i["opponent"] and i["opponent"]["name"] for i in trip["items"])


async def test_demo_cannot_patch_items(env: dict[str, Any]) -> None:
    item = await _first_item(env["client"], "pending")
    r = await env["client"].patch(
        f"/v1/trips/{TRIP}/items/{item['id']}", json={"status": "requested"}
    )
    assert r.status_code == 403
    assert r.json()["type"].endswith("read-only-demo")


async def test_patch_item_transitions_audits_and_emits(env: dict[str, Any]) -> None:
    c, ops = env["client"], env["ops"]
    item = await _first_item(c, "pending")
    url = f"/v1/trips/{TRIP}/items/{item['id']}"

    bad = await c.patch(url, json={"status": "completed"}, headers=ops)
    assert bad.status_code == 409 and bad.json()["type"].endswith("invalid-transition")
    empty = await c.patch(url, json={}, headers=ops)
    assert empty.status_code == 422

    r = await c.patch(url, json={"status": "requested", "notes": "Pedido por mail"}, headers=ops)
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["status"] == "requested" and body["requested_at"] and body["notes"]

    async with shared.system_scope() as s:
        event = await s.scalar(
            select(OutboxEvent)
            .where(OutboxEvent.subject_id == UUID(item["id"]))
            .order_by(OutboxEvent.created_at.desc())
        )
        audit = await s.scalar(
            select(AuditLog).where(
                AuditLog.subject_id == UUID(item["id"]), AuditLog.action == "trip_item.update"
            )
        )
    assert event is not None and event.type == "trip_item.status_changed"
    assert event.payload["item"]["status"] == "requested"
    assert event.payload["item"]["tripId"] == str(TRIP) and event.payload["item"]["kind"]
    assert audit is not None and audit.after == {"status": "requested", "notes": "Pedido por mail"}

    # Notes-only edits are audited but are not status events.
    r = await c.patch(url, json={"notes": "Confirmar hora"}, headers=ops)
    assert r.status_code == 200 and r.json()["status"] == "requested"


async def test_unknown_item_is_404(env: dict[str, Any]) -> None:
    r = await env["client"].patch(
        f"/v1/trips/{TRIP}/items/{uuid4()}", json={"notes": "x"}, headers=env["ops"]
    )
    assert r.status_code == 404


async def test_leads_list_filters_and_pages(env: dict[str, Any]) -> None:
    c = env["client"]
    everything = (await c.get("/v1/leads?limit=200")).json()["items"]
    assert len(everything) >= 3
    created = [item["created_at"] for item in everything]
    assert created == sorted(created, reverse=True)

    qualified = (await c.get("/v1/leads?status=qualified&limit=200")).json()["items"]
    assert qualified and all(item["status"] == "qualified" for item in qualified)
    assert str(LEAD) in {item["id"] for item in qualified}

    seen: list[str] = []
    cursor: str | None = None
    while True:
        query = "/v1/leads?limit=2" + (f"&cursor={cursor}" if cursor else "")
        page = (await c.get(query)).json()
        seen += [item["id"] for item in page["items"]]
        cursor = page["next_cursor"]
        if not cursor:
            break
    assert seen == [item["id"] for item in everything]


async def test_lead_detail(env: dict[str, Any]) -> None:
    c = env["client"]
    lead = (await c.get(f"/v1/leads/{LEAD}")).json()
    assert lead["trip_code"] == "IGS-2711" and lead["account_name"]
    assert (await c.get(f"/v1/leads/{uuid4()}")).status_code == 404


async def test_patch_lead_lost_needs_reason_and_emits(env: dict[str, Any]) -> None:
    c, ops = env["client"], env["ops"]
    leads = (await c.get("/v1/leads?status=qualified&limit=200")).json()["items"]
    target = next(item for item in leads if item["id"] != str(LEAD))
    url = f"/v1/leads/{target['id']}"

    assert (await c.patch(url, json={"status": "lost"})).status_code == 403  # demo
    r = await c.patch(url, json={"status": "lost"}, headers=ops)
    assert r.status_code == 422 and r.json()["type"].endswith("lost-reason-required")
    r = await c.patch(url, json={"status": "won"}, headers=ops)
    assert r.status_code == 409  # qualified → won skips the proposal

    r = await c.patch(
        url, json={"status": "lost", "lost_reason": " Eligió otro operador "}, headers=ops
    )
    assert r.status_code == 200, r.text
    assert r.json()["status"] == "lost" and r.json()["lost_reason"] == "Eligió otro operador"
    async with shared.system_scope() as s:
        event = await s.scalar(
            select(OutboxEvent).where(
                OutboxEvent.subject_id == UUID(target["id"]),
                OutboxEvent.type == "lead.status_changed",
            )
        )
    assert event is not None and event.payload["previousStatus"] == "qualified"

    # Reopening clears the reason.
    r = await c.patch(url, json={"status": "qualified"}, headers=ops)
    assert r.status_code == 200 and r.json()["lost_reason"] is None


async def test_account_interactions_carry_an_excerpt(env: dict[str, Any]) -> None:
    account = (await env["client"].get(f"/v1/accounts/{ACCOUNT}")).json()
    excerpts = [i["excerpt"] for i in account["recent_interactions"]]
    assert excerpts and all(e is None or len(e) <= 280 for e in excerpts)
    assert any(e for e in excerpts)
