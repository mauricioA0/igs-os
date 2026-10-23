"""Approvals, flows, executions and the outbox against a real migrated Postgres (RLS on).

Needs `docker compose up -d db` and a migrated database:

    IGS_TEST_W9_DATABASE_URL=postgresql+asyncpg://igs:igs@localhost:5433/igs_test_w9
    uv run alembic -c packages/py-common/alembic.ini -x url=$IGS_TEST_W9_DATABASE_URL upgrade head

Temporal is replaced by ``RecordingGateway``. Skipped when the database is not reachable.
"""

import json
import os
from collections.abc import AsyncIterator
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any
from uuid import UUID, uuid4

import httpx
import pytest
from sqlalchemy import select, text, update
from sqlalchemy.ext.asyncio import AsyncEngine

from igs_common.db import session as shared
from igs_common.db.models import Approval, FlowExecution, OutboxEvent
from igs_common.domain.approvals import payload_hash
from igs_core.app import create_app
from igs_core.config import Settings
from igs_core.deps import hash_api_key
from igs_core.events.dispatcher import OutboxDispatcher
from igs_core.temporal import RecordingGateway

URL = os.environ.get(
    "IGS_TEST_W9_DATABASE_URL", "postgresql+asyncpg://igs:igs@localhost:5433/igs_test_w9"
)
EXAMPLES = Path(__file__).resolve().parents[3] / "packages" / "flow-schema" / "examples"
pytestmark = pytest.mark.asyncio(loop_scope="session")


def _example(name: str) -> dict[str, Any]:
    return json.loads((EXAMPLES / f"{name}.json").read_text())


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
    os.environ["IGS_DB_APP_ROLE"] = "igs_app"
    tenant = await _seed(engine)
    gateway = RecordingGateway()
    app = create_app(
        Settings(
            environment="test",
            database_url=URL,
            demo_tenant_slug=tenant["slug"],
            mcp_enabled=False,
        ),
        workflows=gateway,
    )
    transport = httpx.ASGITransport(app=app)
    async with (
        app.router.lifespan_context(app),
        httpx.AsyncClient(transport=transport, base_url="http://t") as client,
    ):
        headers = {"Authorization": f"Bearer {tenant['key']}"}
        yield {
            "client": client,
            "headers": headers,
            "gateway": gateway,
            "tenant": tenant,
            "engine": shared.get_engine(),
        }
    os.environ.pop("IGS_DB_APP_ROLE", None)


async def _seed(engine: AsyncEngine) -> dict[str, Any]:
    ids = {"tenant": uuid4(), "user": uuid4()}
    slug = f"w9-{uuid4().hex[:8]}"
    key = f"igs_{slug}"
    async with engine.begin() as conn:
        await conn.execute(
            text("insert into tenants (id, slug, name) values (:tenant, :slug, :label)"),
            {**ids, "slug": slug, "label": slug},
        )
        await conn.execute(
            text(
                "insert into users (id, tenant_id, email, name, role) "
                "values (:user, :tenant, :email, 'Ops', 'ops')"
            ),
            {**ids, "email": f"{slug}@x.test"},
        )
        await conn.execute(
            text(
                "insert into api_keys (id, tenant_id, name, prefix, hash, scopes, created_by) "
                "values (gen_random_uuid(), :tenant, 'ops', 'igs_', :hash, :scopes, :user)"
            ),
            # This key stands in for a signed-in ops person, so it may decide approvals.
            {**ids, "hash": hash_api_key(key), "scopes": ["igs:approve"]},
        )
    return {**ids, "slug": slug, "key": key}


async def _create_and_publish(env: dict[str, Any], name: str) -> dict[str, Any]:
    c, h = env["client"], env["headers"]
    graph = _example(name)
    r = await c.post("/v1/flows", json={"name": graph["name"], "graph": graph}, headers=h)
    assert r.status_code == 201, r.text
    flow = r.json()
    assert r.headers["etag"] == '"rev-1"'
    r = await c.post(
        f"/v1/flows/{flow['id']}/publish",
        json={"changelog": "first"},
        headers={**h, "If-Match": '"rev-1"'},
    )
    assert r.status_code == 201, r.text
    return {"flow": flow, "version": r.json()}


async def test_demo_is_read_only(env: dict[str, Any]) -> None:
    c = env["client"]
    assert (await c.get("/v1/flows")).status_code == 200
    r = await c.post("/v1/flows", json={"name": "x", "graph": {"id": "x"}})
    assert r.status_code == 403
    assert r.json()["type"].endswith("read-only-demo")
    # The demo copilot may propose approvals, but deciding one is never allowed.
    r = await c.post(
        f"/v1/approvals/{uuid4()}/decision",
        json={"decision": "approved", "payload_hash": "sha256:" + "0" * 64},
    )
    assert r.status_code == 403
    assert r.json()["type"].endswith("read-only-demo")


async def test_flow_draft_concurrency_validate_and_publish(env: dict[str, Any]) -> None:
    c, h = env["client"], env["headers"]
    graph = _example("post-match-report")
    r = await c.post("/v1/flows", json={"name": "PMR", "graph": graph}, headers=h)
    assert r.status_code == 201
    flow_id = r.json()["id"]
    assert (
        await c.post("/v1/flows", json={"name": "PMR", "graph": graph}, headers=h)
    ).status_code == 409

    url = f"/v1/flows/{flow_id}/draft"
    assert (await c.put(url, json={"graph": graph}, headers=h)).status_code == 428
    r = await c.put(url, json={"graph": graph}, headers={**h, "If-Match": '"rev-1"'})
    assert r.status_code == 200 and r.headers["etag"] == '"rev-2"'
    stale = await c.put(url, json={"graph": graph}, headers={**h, "If-Match": '"rev-1"'})
    assert stale.status_code == 412 and stale.headers["etag"] == '"rev-2"'

    broken = {**graph, "edges": [*graph["edges"], {"from": "nope", "to": "nowhere"}]}
    r = await c.post(f"/v1/flows/{flow_id}/validate", json={"graph": broken}, headers=h)
    assert r.status_code == 200 and r.json()["ok"] is False

    r = await c.put(url, json={"graph": broken}, headers={**h, "If-Match": "rev-2"})
    assert r.status_code == 200
    r = await c.post(f"/v1/flows/{flow_id}/publish", headers={**h, "If-Match": '"rev-3"'})
    assert r.status_code == 422
    assert r.json()["errors"], "problems are returned for the editor"

    r = await c.put(url, json={"graph": graph}, headers={**h, "If-Match": '"rev-3"'})
    r = await c.post(f"/v1/flows/{flow_id}/publish", headers={**h, "If-Match": '"rev-4"'})
    assert r.status_code == 201, r.text
    assert r.json()["version"] == 1
    r = await c.put(url, json={"graph": graph}, headers={**h, "If-Match": '"rev-4"'})
    r = await c.post(f"/v1/flows/{flow_id}/publish", headers={**h, "If-Match": '"rev-5"'})
    assert r.json()["version"] == 2

    versions = (await c.get(f"/v1/flows/{flow_id}/versions", headers=h)).json()
    assert [v["version"] for v in versions] == [2, 1]
    one = (await c.get(f"/v1/flows/{flow_id}/versions/1", headers=h)).json()
    assert one["graph"]["version"] == 1
    detail = (await c.get(f"/v1/flows/{flow_id}", headers=h)).json()
    assert detail["published_version"] == 2


async def test_manual_execution_and_detail(env: dict[str, Any]) -> None:
    c, h, gw = env["client"], env["headers"], env["gateway"]
    published = await _create_and_publish(env, "inbound-inquiry")
    flow_id = published["flow"]["id"]
    r = await c.post(
        f"/v1/flows/{flow_id}/executions", json={"trigger": {"message": "hi"}}, headers=h
    )
    assert r.status_code == 202, r.text
    execution = r.json()
    wf = execution["temporal_workflow_id"]
    assert wf == f"man-{execution['id']}"
    assert gw.started[wf]["flow"]["version"] == 1
    assert gw.started[wf]["execution_id"] == execution["id"]

    detail = (await c.get(f"/v1/executions/{execution['id']}", headers=h)).json()
    assert detail["flow_key"] == "inbound-inquiry" and detail["node_runs"] == []
    listed = (await c.get(f"/v1/executions?flow_id={flow_id}", headers=h)).json()
    assert [e["id"] for e in listed["items"]] == [execution["id"]]

    r = await c.post(f"/v1/executions/{execution['id']}/cancel", headers=h)
    assert r.status_code == 202
    assert gw.signals[-1][:2] == (wf, "cancel")
    env["execution"] = execution


async def test_failed_start_marks_execution_failed(env: dict[str, Any]) -> None:
    c, h, gw = env["client"], env["headers"], env["gateway"]
    flow_id = (await c.get("/v1/flows", headers=h)).json()
    inbound = next(f for f in flow_id if f["key"] == "inbound-inquiry")
    gw.fail = True
    try:
        r = await c.post(f"/v1/flows/{inbound['id']}/executions", json={}, headers=h)
    finally:
        gw.fail = False
    assert r.status_code == 502
    failed = (await c.get("/v1/executions?status=failed", headers=h)).json()["items"]
    assert failed and failed[0]["status"] == "failed"


async def test_approval_decisions(env: dict[str, Any]) -> None:
    c, h, gw = env["client"], env["headers"], env["gateway"]
    execution = env["execution"]
    params = {"to": "coach@lakeshore.example", "trip": "t-2711"}
    tenant_id: UUID = env["tenant"]["tenant"]
    async with shared.session_scope(tenant_id) as s:
        a1 = Approval(
            tenant_id=tenant_id,
            execution_id=UUID(execution["id"]),
            node_id="ops_review",
            title="Send proposal",
            proposed_action={"action": "send_proposal", "params": params},
            payload_hash=payload_hash("send_proposal", params),
            risk_class="external",
            assignee_role="ops",
        )
        a2 = Approval(
            tenant_id=tenant_id,
            execution_id=UUID(execution["id"]),
            node_id="ops_review",
            title="Send proposal (v2)",
            proposed_action={"action": "send_proposal", "params": params},
            payload_hash=payload_hash("send_proposal", params),
            risk_class="external",
            assignee_role="ops",
        )
        s.add_all([a1, a2])
        await s.flush()
        ids = (str(a1.id), str(a2.id))

    pending = (await c.get("/v1/approvals?status=pending", headers=h)).json()["items"]
    assert {p["id"] for p in pending} >= set(ids)
    one = (await c.get(f"/v1/approvals/{ids[0]}", headers=h)).json()
    good_hash = one["payload_hash"]

    url = f"/v1/approvals/{ids[0]}/decision"
    r = await c.post(url, json={"decision": "approved", "payload_hash": "sha256:bad"}, headers=h)
    assert r.status_code == 409 and r.json()["type"].endswith("approval-changed")
    r = await c.post(
        url, json={"decision": "approved", "payload_hash": good_hash, "comment": "ok"}, headers=h
    )
    assert r.status_code == 200, r.text
    assert r.json()["approval"]["status"] == "approved"
    assert r.json()["signal_delivered"] is True
    wf, signal, body = gw.signals[-1]
    assert (wf, signal) == (execution["temporal_workflow_id"], "approval_decision")
    assert body["node_id"] == "ops_review" and body["decision"] == "approved"
    again = await c.post(url, json={"decision": "rejected", "payload_hash": good_hash}, headers=h)
    assert again.status_code == 409

    edited = {"action": "send_proposal", "params": {**params, "note": "10% discount"}}
    r = await c.post(
        f"/v1/approvals/{ids[1]}/decision",
        json={"decision": "approved", "payload_hash": good_hash, "edited_action": edited},
        headers=h,
    )
    assert r.status_code == 200, r.text
    out = r.json()
    assert out["superseded"] == ids[1]
    assert out["approval"]["id"] != ids[1]
    assert out["approval"]["payload_hash"] == payload_hash("send_proposal", edited["params"])
    old = (await c.get(f"/v1/approvals/{ids[1]}", headers=h)).json()
    assert old["status"] == "superseded" and old["superseded_by"] == out["approval"]["id"]
    assert gw.signals[-1][2]["form"]["edited_action"] == edited


async def test_expired_approvals_report_expired_everywhere(env: dict[str, Any]) -> None:
    """QA D-03/D-12: one effective status for lists, detail and counts; rejections need a why."""
    c, h = env["client"], env["headers"]
    tenant_id: UUID = env["tenant"]["tenant"]
    params = {"to": "coach@lakeshore.example"}
    now = datetime.now(UTC)
    async with shared.session_scope(tenant_id) as s:
        late = Approval(
            tenant_id=tenant_id,
            title="Move the match (overdue)",
            proposed_action={"action": "send_proposal", "params": params},
            payload_hash=payload_hash("send_proposal", params),
            risk_class="external",
            assignee_role="ops",
            expires_at=now - timedelta(hours=7),
        )
        fresh = Approval(
            tenant_id=tenant_id,
            title="Send proposal (fresh)",
            proposed_action={"action": "send_proposal", "params": params},
            payload_hash=payload_hash("send_proposal", params),
            risk_class="external",
            assignee_role="ops",
            expires_at=now + timedelta(days=2),
        )
        s.add_all([late, fresh])
        await s.flush()
        late_id, fresh_id = str(late.id), str(fresh.id)

    before = (await c.get("/v1/approvals/counts", headers=h)).json()
    pending = {
        a["id"] for a in (await c.get("/v1/approvals?status=pending", headers=h)).json()["items"]
    }
    expired = {
        a["id"] for a in (await c.get("/v1/approvals?status=expired", headers=h)).json()["items"]
    }
    assert fresh_id in pending and late_id not in pending
    assert late_id in expired and fresh_id not in expired
    detail = (await c.get(f"/v1/approvals/{late_id}", headers=h)).json()
    assert detail["status"] == "expired"
    assert before["expired"] >= 1 and before["pending"] >= 1

    r = await c.post(
        f"/v1/approvals/{late_id}/decision",
        json={"decision": "approved", "payload_hash": detail["payload_hash"]},
        headers=h,
    )
    assert r.status_code == 409 and r.json()["type"].endswith("expired")
    r = await c.post(
        f"/v1/approvals/{fresh_id}/decision",
        json={"decision": "rejected", "payload_hash": detail["payload_hash"], "comment": "  "},
        headers=h,
    )
    assert r.status_code == 422 and r.json()["type"].endswith("reason-required")
    r = await c.post(
        f"/v1/approvals/{fresh_id}/decision",
        json={
            "decision": "rejected",
            "payload_hash": detail["payload_hash"],
            "comment": "Fuera de política",
        },
        headers=h,
    )
    assert r.status_code == 200, r.text
    after = (await c.get("/v1/approvals/counts", headers=h)).json()
    assert after["pending"] == before["pending"] - 1 and after["rejected"] == before["rejected"] + 1


async def test_outbox_dispatch_is_idempotent(env: dict[str, Any]) -> None:
    c, h, gw = env["client"], env["headers"], env["gateway"]
    await _create_and_publish(env, "pre-departure-check")
    trip = uuid4()
    confirmed = {"trip": {"status": "confirmed", "id": str(trip)}, "previousStatus": "proposed"}
    r = await c.post(
        "/v1/events",
        json={
            "type": "trip.status_changed",
            "subject_type": "trip",
            "subject_id": str(trip),
            "payload": confirmed,
        },
        headers=h,
    )
    assert r.status_code == 202, r.text
    event_id = r.json()["id"]
    skip = {**confirmed, "previousStatus": "confirmed"}
    r = await c.post(
        "/v1/events",
        json={
            "type": "trip.status_changed",
            "subject_type": "trip",
            "subject_id": str(trip),
            "payload": skip,
        },
        headers=h,
    )

    dispatcher = OutboxDispatcher(gw, engine=env["engine"])
    before = set(gw.started)
    while (await dispatcher.run_once()).events:
        pass
    started = [w for w in gw.started if w not in before and w.startswith(f"evt-{event_id}-")]
    assert len(started) == 1, "only the matching event starts the flow"

    # Redelivery (e.g. crash before commit): same workflow id, no second execution row.
    async with shared.system_scope() as s:
        await s.execute(
            update(OutboxEvent).where(OutboxEvent.id == UUID(event_id)).values(dispatched_at=None)
        )
    await dispatcher.run_once()
    async with shared.system_scope() as s:
        rows = (
            await s.scalars(
                select(FlowExecution).where(FlowExecution.temporal_workflow_id == started[0])
            )
        ).all()
    assert len(rows) == 1 and rows[0].subject_id == trip

    pending = (await c.get("/v1/events?pending=true", headers=h)).json()
    assert all(e["dispatched_at"] for e in pending) or pending == []


async def test_stream_ends_for_finished_execution(env: dict[str, Any]) -> None:
    c, h = env["client"], env["headers"]
    execution_id = env["execution"]["id"]
    async with shared.system_scope() as s:
        await s.execute(
            update(FlowExecution)
            .where(FlowExecution.id == UUID(execution_id))
            .values(status="succeeded")
        )
    async with c.stream("GET", f"/v1/executions/{execution_id}/stream", headers=h) as r:
        assert r.status_code == 200
        body = ""
        async for chunk in r.aiter_text():
            body += chunk
            if "event: snapshot" in body:
                break
    assert "event: snapshot" in body


async def test_agent_keys_cannot_approve(env: dict[str, Any]) -> None:
    """A key without igs:approve (e.g. handed to Claude Code over MCP) can't decide over REST."""
    c, h = env["client"], env["headers"]
    tenant = env["tenant"]
    agent_key = f"igs_agent_{uuid4().hex}"
    async with shared.system_scope() as s:
        await s.execute(
            text(
                "insert into api_keys (id, tenant_id, name, prefix, hash, scopes, created_by) "
                "values (gen_random_uuid(), :tenant, 'agent', 'igs_', :hash, :scopes, :user)"
            ),
            {
                "tenant": tenant["tenant"],
                "user": tenant["user"],
                "hash": hash_api_key(agent_key),
                "scopes": ["igs:read", "igs:write", "igs:external"],
            },
        )
    params = {"to": "coach@lakeshore.example", "trip": "t-2711"}
    async with shared.session_scope(tenant["tenant"]) as s:
        row = Approval(
            tenant_id=tenant["tenant"],
            execution_id=UUID(env["execution"]["id"]),
            node_id="ops_review",
            title="Send proposal (agent key)",
            proposed_action={"action": "send_proposal", "params": params},
            payload_hash=payload_hash("send_proposal", params),
            risk_class="external",
            assignee_role="ops",
        )
        s.add(row)
        await s.flush()
        approval_id, good_hash = str(row.id), row.payload_hash

    url = f"/v1/approvals/{approval_id}/decision"
    body = {"decision": "approved", "payload_hash": good_hash}
    r = await c.post(url, json=body, headers={"Authorization": f"Bearer {agent_key}"})
    assert r.status_code == 403 and r.json()["type"].endswith("human-approval-required")
    still = (await c.get(f"/v1/approvals/{approval_id}", headers=h)).json()
    assert still["status"] == "pending"
