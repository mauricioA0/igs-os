"""Lead intake end to end against real Postgres: form + email in, lead/approval/clock out.

The database (``igs_test_c9``) is created and migrated by ``conftest.py`` and seeded here with
the demo tenant. Two apps share it: ``open`` (demo mode, nothing configured: unsigned posts
land in the demo tenant) and ``signed`` (HMAC secret + site key: unsigned posts are refused).
"""

import hashlib
import hmac
import os
import time
from collections.abc import AsyncIterator
from pathlib import Path
from typing import Any
from uuid import UUID, uuid4

import httpx
import pytest
from pydantic import SecretStr
from sqlalchemy import select, text

from igs_common.db import session as shared
from igs_common.db.models import Approval, Contact, Lead, LeadIntake, OutboxEvent
from igs_common.llm import FakeLLM, Scripted
from igs_common.seed import fixture_id, load
from igs_common.testing import database_url
from igs_core.app import create_app
from igs_core.config import Settings
from igs_core.deps import hash_api_key
from igs_core.ratelimit import RateLimiter
from igs_core.temporal import RecordingGateway

URL = database_url("igs_test_c9", driver="postgresql+asyncpg")
SECRET = "c9-test-secret"  # noqa: S105 - test-only HMAC key
SITE_KEY = "pk_igs_site_c9"
ORIGIN = "https://infinityglobalsports.com"
RIVERSIDE = fixture_id("igs", "account", "acc-riverside")
LAKESHORE = fixture_id("igs", "account", "acc-lakeshore")
EMAILS = Path(__file__).parents[3] / "packages/py-common/tests/intake/fixtures"
pytestmark = pytest.mark.asyncio(loop_scope="session")


def _form(**overrides: Any) -> dict[str, Any]:
    base = {
        "first_name": "Jordan",
        "last_name": "Ellis",
        "program": "Cedar Falls Prep",
        "role": "Athletic Director",
        "email": f"jellis+{uuid4().hex[:8]}@cedarfalls.example.edu",
        "phone_country_code": "+1",
        "phone": "515 555 0199",
        "travel_window": "Spring break 2027",
        "how_heard": "Google Search",
        "message": "Girls varsity soccer, maybe 20 players. What would a tour look like?",
        "landing_page": "/private-school-sports-tours",
        "website": "",
    }
    return {**base, **overrides}


def _sign(body: bytes, *, secret: str = SECRET, at: int | None = None) -> dict[str, str]:
    ts = str(at if at is not None else int(time.time()))
    digest = hmac.new(secret.encode(), ts.encode() + b"." + body, hashlib.sha256).hexdigest()
    return {"X-IGS-Timestamp": ts, "X-IGS-Signature": f"sha256={digest}"}


@pytest.fixture(scope="module")
async def env() -> AsyncIterator[dict[str, Any]]:
    engine = shared.configure(URL)
    try:
        async with shared.system_scope() as session:
            await load(session)
    except OSError:
        await shared.dispose()
        pytest.skip("Postgres not reachable")
    key = f"igs_c9_{uuid4().hex}"
    async with engine.begin() as conn:
        tenant = await conn.scalar(text("select id from tenants where slug = 'igs'"))
        user = uuid4()
        await conn.execute(
            text(
                "insert into users (id, tenant_id, email, name, role) "
                "values (:user, :tenant, :email, 'Ops C9', 'ops')"
            ),
            {"user": user, "tenant": tenant, "email": f"{user.hex}@c9.test"},
        )
        await conn.execute(
            text(
                "insert into api_keys (id, tenant_id, name, prefix, hash, scopes, created_by) "
                "values (gen_random_uuid(), :tenant, 'ops-c9', 'igs_', :hash, :scopes, :user)"
            ),
            {
                "tenant": tenant,
                "hash": hash_api_key(key),
                "scopes": ["igs:write", "igs:approve"],
                "user": user,
            },
        )
    os.environ["IGS_DB_APP_ROLE"] = "igs_app"
    open_app = create_app(
        Settings(environment="test", database_url=URL, demo_tenant_slug="igs", mcp_enabled=False),
        workflows=RecordingGateway(),
    )
    signed_app = create_app(
        Settings(
            environment="test",
            database_url=URL,
            demo_tenant_slug="igs",
            mcp_enabled=False,
            intake_hmac_secret=SecretStr(SECRET),
            intake_site_key=SITE_KEY,
            intake_allowed_origins=[ORIGIN],
            intake_tenant_slug="igs",
        ),
        workflows=RecordingGateway(),
    )
    for app in (open_app, signed_app):
        app.state.intake_llm = None  # rules only unless a test scripts a model
    async with (
        open_app.router.lifespan_context(open_app),
        signed_app.router.lifespan_context(signed_app),
        httpx.AsyncClient(
            transport=httpx.ASGITransport(app=open_app), base_url="http://t"
        ) as open_client,
        httpx.AsyncClient(
            transport=httpx.ASGITransport(app=signed_app), base_url="http://t"
        ) as signed_client,
    ):
        yield {
            "open": open_client,
            "signed": signed_client,
            "apps": (open_app, signed_app),
            "ops": {"Authorization": f"Bearer {key}"},
            "tenant": tenant,
        }
    os.environ.pop("IGS_DB_APP_ROLE", None)


@pytest.fixture(autouse=True)
def _fresh_limits(env: dict[str, Any]) -> None:
    for app in env["apps"]:
        app.state.public_rate_limiter = RateLimiter()


async def _intake(intake_id: str) -> LeadIntake:
    async with shared.system_scope() as session:
        row = await session.get(LeadIntake, UUID(intake_id))
        assert row is not None
        session.expunge(row)
        return row


async def _approval(approval_id: UUID | None) -> Approval:
    assert approval_id is not None
    async with shared.system_scope() as session:
        row = await session.get(Approval, approval_id)
        assert row is not None
        session.expunge(row)
        return row


# ── Form ──────────────────────────────────────────────────────────────────────


async def test_form_creates_contact_intake_and_reply_approval(env: dict[str, Any]) -> None:
    body = _form()
    res = await env["open"].post("/v1/intake/form", json=body)
    assert res.status_code == 202, res.text
    out = res.json()
    assert out["status"] == "received" and out["reply_by"]

    intake = await _intake(out["id"])
    assert intake.channel == "form" and intake.status == "open"
    assert intake.relationship == "new"
    assert "destination_country" in intake.missing and "group_size" not in intake.missing
    assert intake.extracted["values"]["gender"] == "women"
    assert intake.extracted["evidence"]["group_size"] == "20 players"
    assert intake.submitted["landing_page"] == "/private-school-sports-tours"
    assert "website" not in intake.submitted
    assert any(r["reason"].startswith("Escribe quien decide") for r in intake.score_reasons)

    approval = await _approval(intake.approval_id)
    assert approval.status.value == "pending" and approval.assignee_role.value == "ops"
    assert approval.proposed_action["action"] == "send_email"
    params = approval.proposed_action["params"]
    assert params["to"] == body["email"]
    assert params["body"].startswith("Hi Jordan,")
    assert "Argentina, Brazil, Costa Rica or Spain" in params["body"]
    assert approval.details["intake_id"] == out["id"]
    assert approval.details["sla_due_at"] == intake.sla_due_at.isoformat()

    async with shared.system_scope() as session:
        contact = await session.get(Contact, intake.contact_id)
        assert contact is not None and contact.organization == "Cedar Falls Prep"
        assert contact.phone == "+1 515 555 0199"
        events = (
            await session.scalars(select(OutboxEvent).where(OutboxEvent.subject_id == intake.id))
        ).all()
        assert [e.type for e in events] == ["intake.received"]


async def test_resubmitting_the_same_form_is_idempotent(env: dict[str, Any]) -> None:
    body = _form()
    first = await env["open"].post("/v1/intake/form", json=body)
    again = await env["open"].post("/v1/intake/form", json=body)
    assert first.json()["id"] == again.json()["id"]
    async with shared.system_scope() as session:
        count = await session.scalar(
            select(text("count(*)"))
            .select_from(Approval)
            .where(Approval.subject_id == UUID(first.json()["id"]))
        )
    assert count == 1


async def test_urlencoded_form_is_accepted(env: dict[str, Any]) -> None:
    body = _form(message="Boys JV basketball, 12 players")
    res = await env["open"].post("/v1/intake/form", data=body)
    assert res.status_code == 202, res.text
    intake = await _intake(res.json()["id"])
    assert intake.extracted["values"]["sport"] == "basketball"


async def test_honeypot_is_stored_as_spam_without_contact_or_reply(env: dict[str, Any]) -> None:
    res = await env["open"].post("/v1/intake/form", json=_form(website="http://seo.example"))
    assert res.status_code == 202  # bots get the same answer as people
    intake = await _intake(res.json()["id"])
    assert intake.status == "spam"
    assert intake.contact_id is None and intake.approval_id is None


async def test_invalid_form_is_422(env: dict[str, Any]) -> None:
    res = await env["open"].post("/v1/intake/form", json=_form(email="nope"))
    assert res.status_code == 422
    assert "email" in res.json()["detail"]


async def test_form_is_rate_limited(env: dict[str, Any]) -> None:
    codes = [
        (await env["open"].post("/v1/intake/form", json=_form())).status_code for _ in range(6)
    ]
    assert codes[:5] == [202] * 5 and codes[5] == 429


async def test_returning_customer_is_recognized_and_scored(env: dict[str, Any]) -> None:
    # Marcus Hale's club (Riverside) has a confirmed trip in the seed.
    body = _form(
        first_name="Marcus",
        last_name="Hale",
        program="Riverside FC Academy",
        role="Head Coach",
        email="MHale@riversidefc.example",
        how_heard="Returning Customer",
        message="U17 boys again, ECNL. 22 players, Buenos Aires.",
    )
    res = await env["open"].post("/v1/intake/form", json=body)
    intake = await _intake(res.json()["id"])
    assert intake.relationship == "returning_customer"
    assert intake.account_id == RIVERSIDE
    assert intake.score_reasons[0] == {"points": 25, "reason": "Cliente que ya viajó con IGS"}
    approval = await _approval(intake.approval_id)
    assert "Great to hear from you again" in approval.proposed_action["params"]["body"]


async def test_claimed_returning_customer_without_trips_is_flagged(env: dict[str, Any]) -> None:
    body = _form(how_heard="Returning Customer")
    intake = await _intake((await env["open"].post("/v1/intake/form", json=body)).json()["id"])
    assert intake.relationship == "new"
    assert any("verificar" in r["reason"] for r in intake.score_reasons)


async def test_program_name_matches_the_account(env: dict[str, Any]) -> None:
    body = _form(program="lakeshore university", email=f"newcoach{uuid4().hex[:6]}@gmail.com")
    intake = await _intake((await env["open"].post("/v1/intake/form", json=body)).json()["id"])
    assert intake.account_id == LAKESHORE and intake.relationship == "known_contact"


# ── Auth ──────────────────────────────────────────────────────────────────────


async def test_signed_app_refuses_unsigned_and_bad_signatures(env: dict[str, Any]) -> None:
    body = httpx.Request("POST", "http://t", json=_form()).content
    headers = {"content-type": "application/json"}
    unsigned = await env["signed"].post("/v1/intake/form", content=body, headers=headers)
    assert unsigned.status_code == 401
    forged = _sign(body, secret="other")  # noqa: S106
    wrong = await env["signed"].post("/v1/intake/form", content=body, headers={**headers, **forged})
    assert wrong.status_code == 401
    stale = await env["signed"].post(
        "/v1/intake/form",
        content=body,
        headers={**headers, **_sign(body, at=int(time.time()) - 3600)},
    )
    assert stale.status_code == 401
    good = await env["signed"].post(
        "/v1/intake/form", content=body, headers={**headers, **_sign(body)}
    )
    assert good.status_code == 202, good.text


async def test_site_key_needs_an_allowed_origin(env: dict[str, Any]) -> None:
    key = {"X-IGS-Site-Key": SITE_KEY}
    elsewhere = await env["signed"].post(
        "/v1/intake/form", json=_form(), headers={**key, "Origin": "https://evil.example"}
    )
    assert elsewhere.status_code == 401
    ok = await env["signed"].post(
        "/v1/intake/form", json=_form(), headers={**key, "Origin": ORIGIN}
    )
    assert ok.status_code == 202
    email = (EMAILS / "html_only.eml").read_bytes()
    no_site_key_for_email = await env["signed"].post(
        "/v1/intake/email", content=email, headers={**key, "Origin": ORIGIN}
    )
    assert no_site_key_for_email.status_code == 401


# ── Email ─────────────────────────────────────────────────────────────────────


async def test_forwarded_email_with_everything_creates_the_lead(env: dict[str, Any]) -> None:
    raw = (EMAILS / "gmail_forward.eml").read_bytes()
    raw = raw.replace(b"CAF8x1-gmail-fwd-0001", f"fwd-{uuid4().hex}".encode())
    headers = {"content-type": "message/rfc822", **_sign(raw)}
    res = await env["signed"].post("/v1/intake/email", content=raw, headers=headers)
    assert res.status_code == 202, res.text
    intake = await _intake(res.json()["id"])
    assert intake.channel == "email" and intake.status == "lead_created"
    assert intake.missing == []
    assert intake.submitted["forwarded_by"] == "sortega@infinityglobalsports.example"
    async with shared.system_scope() as session:
        lead = await session.get(Lead, intake.lead_id)
        assert lead is not None
        assert (lead.sport.value, lead.gender.value, lead.level_score) == ("soccer", "women", 7)
        assert (lead.group_size, lead.duration_days, lead.destination_country) == (
            26,
            10,
            "Argentina",
        )
        assert lead.source.value == "webhook" and lead.contact_id == intake.contact_id
        types = {
            e.type
            for e in (
                await session.scalars(
                    select(OutboxEvent).where(OutboxEvent.subject_id.in_([intake.id, lead.id]))
                )
            ).all()
        }
    assert types == {"intake.received", "lead.created"}
    approval = await _approval(intake.approval_id)
    params = approval.proposed_action["params"]
    assert params["subject"] == "Re: Spring 2027 tour inquiry - Harbor State WSOC"
    assert params["to"] == "pnatarajan@harborstate.example.edu"
    assert "we'll send them shortly" in params["body"]

    leads = await env["signed"].get("/v1/leads", headers=env["ops"])
    assert str(intake.lead_id) in {item["id"] for item in leads.json()["items"]}


async def test_the_same_email_twice_is_one_intake(env: dict[str, Any]) -> None:
    raw = (EMAILS / "outlook_attached.eml").read_bytes()
    raw = raw.replace(b"outlook-attached-0003", f"oa-{uuid4().hex}".encode())
    first = await env["signed"].post("/v1/intake/email", content=raw, headers=_sign(raw))
    second = await env["signed"].post("/v1/intake/email", content=raw, headers=_sign(raw))
    assert first.json()["id"] == second.json()["id"]


async def test_unreadable_email_is_422(env: dict[str, Any]) -> None:
    raw = b"Subject: nobody sent this\n\nhello"
    res = await env["signed"].post("/v1/intake/email", content=raw, headers=_sign(raw))
    assert res.status_code == 422


async def test_follow_up_email_fills_the_gaps_and_restarts_the_clock(env: dict[str, Any]) -> None:
    address = f"coach{uuid4().hex[:6]}@cedarfalls.example.edu"
    first = await env["open"].post(
        "/v1/intake/form", json=_form(email=address, message="Women's soccer, 20 players.")
    )
    before = await _intake(first.json()["id"])
    assert "destination_country" in before.missing
    reply = (
        f"From: Jordan Ellis <{address}>\n"
        "To: sales@infinityglobalsports.example\n"
        "Subject: Re: Your Cedar Falls Prep tour with Infinity Global Sports\n"
        f"Message-ID: <follow-{uuid4().hex}@cedarfalls.example.edu>\n"
        "In-Reply-To: <draft@infinityglobalsports.example>\n\n"
        "Argentina, please. We're varsity, high school, 9 days starting March 20, 2027.\n\n"
        "On Thu, Oct 22, 2026 at 3:10 PM IGS wrote:\n> Which destination\n"
    ).encode()
    res = await env["open"].post("/v1/intake/email", content=reply)
    assert res.json()["id"] == first.json()["id"]  # same intake, not a new one
    after = await _intake(first.json()["id"])
    values = after.extracted["values"]
    assert values["group_size"] == 20 and values["gender"] == "women"  # kept
    assert values["destination_country"] == "Argentina" and values["duration_days"] == 9
    assert after.status == "lead_created" and after.lead_id is not None
    assert len(after.submitted["follow_ups"]) == 1
    old = await _approval(before.approval_id)
    assert old.status.value == "superseded" and old.superseded_by == after.approval_id
    new = await _approval(after.approval_id)
    assert new.status.value == "pending"
    assert new.proposed_action["params"]["subject"].startswith("Re: Your Cedar Falls Prep")


# ── Model extraction ──────────────────────────────────────────────────────────


async def test_model_extraction_drops_unbacked_values(env: dict[str, Any]) -> None:
    app = env["apps"][0]
    app.state.intake_llm = FakeLLM(
        [
            Scripted(
                json={
                    "sport": "rugby",
                    "gender": "men",
                    "age_group": None,
                    "level_label": None,
                    "group_size": 35,  # the coach never said a number
                    "destination_country": "Argentina",
                    "travel_date": None,
                    "travel_month": None,
                    "duration_days": None,
                    "budget_per_person_usd": None,
                    "goals": "play local clubs",
                    "evidence": [
                        {"field": "sport", "quote": "men's rugby"},
                        {"field": "gender", "quote": "men's rugby"},
                        {"field": "group_size", "quote": "35 players"},
                        {"field": "destination_country", "quote": "Argentina"},
                        {"field": "goals", "quote": "play local clubs"},
                    ],
                }
            )
        ]
    )
    try:
        body = _form(message="Our men's rugby side wants to play local clubs in Argentina.")
        intake = await _intake((await env["open"].post("/v1/intake/form", json=body)).json()["id"])
    finally:
        app.state.intake_llm = None
    assert intake.extracted["method"] == "llm" and intake.extraction_model == "fake-model"
    assert intake.extracted["values"]["group_size"] is None
    assert intake.extracted["rejected"] == {
        "group_size": "evidence is not a verbatim span of the inquiry"
    }
    assert intake.extracted["values"]["sport"] == "rugby"


# ── Ops: list, detail, SLA, approval stops the clock ─────────────────────────


async def test_approving_the_reply_stops_the_clock(env: dict[str, Any]) -> None:
    res = await env["open"].post("/v1/intake/form", json=_form())
    intake = await _intake(res.json()["id"])
    approval = await _approval(intake.approval_id)

    listed = await env["open"].get("/v1/intake", headers=env["ops"])
    assert listed.status_code == 200
    row = next(r for r in listed.json() if r["id"] == str(intake.id))
    assert row["sla_state"] in {"on_track", "at_risk"} and row["first_response_at"] is None
    dues = [r["sla_due_at"] for r in listed.json()]
    assert dues == sorted(dues)
    sla_before = (await env["open"].get("/v1/intake/sla", headers=env["ops"])).json()

    decided = await env["open"].post(
        f"/v1/approvals/{approval.id}/decision",
        headers=env["ops"],
        json={"decision": "approved", "payload_hash": approval.payload_hash},
    )
    assert decided.status_code == 200, decided.text

    detail = (await env["open"].get(f"/v1/intake/{intake.id}", headers=env["ops"])).json()
    assert detail["first_response_at"] is not None and detail["sla_state"] == "met"
    assert detail["score_reasons"] and detail["extracted"]["values"]
    sla_after = (await env["open"].get("/v1/intake/sla", headers=env["ops"])).json()
    assert sla_after["open"] == sla_before["open"] - 1
    assert sla_after["met_last_7_days"] == sla_before["met_last_7_days"] + 1


async def test_edit_and_approve_also_stops_the_clock(env: dict[str, Any]) -> None:
    intake = await _intake((await env["open"].post("/v1/intake/form", json=_form())).json()["id"])
    approval = await _approval(intake.approval_id)
    params = {**approval.proposed_action["params"], "body": "Hi Jordan, edited by a human."}
    res = await env["open"].post(
        f"/v1/approvals/{approval.id}/decision",
        headers=env["ops"],
        json={
            "decision": "approved",
            "payload_hash": approval.payload_hash,
            "edited_action": {"action": "send_email", "params": params},
        },
    )
    assert res.status_code == 200, res.text
    assert (await _intake(str(intake.id))).first_response_at is not None


async def test_public_demo_sees_inquiries_without_contact_details(env: dict[str, Any]) -> None:
    body = _form()
    intake_id = (await env["open"].post("/v1/intake/form", json=body)).json()["id"]
    detail = (await env["open"].get(f"/v1/intake/{intake_id}")).json()
    assert detail["contact_email"].startswith("j***@")
    assert (
        detail["submitted"]["email"].startswith("j***@") and detail["submitted"]["phone"] == "***"
    )
    ops = (await env["open"].get(f"/v1/intake/{intake_id}", headers=env["ops"])).json()
    assert ops["contact_email"] == body["email"]


async def test_unknown_intake_is_404(env: dict[str, Any]) -> None:
    res = await env["open"].get(f"/v1/intake/{uuid4()}", headers=env["ops"])
    assert res.status_code == 404
