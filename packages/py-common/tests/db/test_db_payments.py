"""Payments against Postgres: trip ledger → positions, idempotent approvals, release."""

import uuid
from datetime import date

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncEngine

from igs_common.db import session_scope
from igs_common.db.enums import (
    AccountKind,
    ApprovalStatus,
    StakeholderRole,
    TravelerRole,
    TripStatus,
)
from igs_common.db.models import Account, Approval, OutboxEvent, Stakeholder, Traveler, Trip
from igs_common.db.rls import APP_ROLE
from igs_common.payments import ItemKind, Stage
from igs_common.payments.inbox import SEND_EVENT, release_approved
from igs_common.payments.service import payment_positions, queue_reminders

from .test_db_rls import _make_tenant

TODAY = date(2026, 10, 22)


async def _seed(engine: AsyncEngine, tenant: uuid.UUID, *, invoices: bool) -> uuid.UUID:
    async with session_scope(tenant, engine=engine, role=APP_ROLE) as s:
        trip = (await s.scalars(select(Trip))).one()
        account = Account(
            tenant_id=tenant, name="Lakeshore U", kind=AccountKind.UNIVERSITY, country="US"
        )
        s.add(account)
        await s.flush()
        s.add_all(
            [
                Stakeholder(
                    tenant_id=tenant,
                    account_id=account.id,
                    name="Dana Whitfield",
                    role=StakeholderRole.COACH,
                    email="dana@lakeshore.example",
                ),
                Stakeholder(
                    tenant_id=tenant,
                    account_id=account.id,
                    name="Robert Haines",
                    role=StakeholderRole.ATHLETIC_DIRECTOR,
                    email="rob@lakeshore.example",
                ),
            ]
        )
        trip.status = TripStatus.PROPOSED
        trip.code = "IGS-2711"
        trip.account_id = account.id
        trip.travelers = 24
        pricing: dict = {"payment_terms": {"enrollment_due": "2026-10-15"}, "paid_usd": 0}
        if invoices:
            # What the importer writes (igs_common.importer.apply.payments_).
            pricing["payments"] = {
                "INV-1042": {"kind": "enrollment_fee", "amount_usd": 2280,
                             "due_date": "2026-10-15", "paid_at": "2026-10-14"},
                "INV-1043": {"kind": "installment", "amount_usd": 12000,
                             "due_date": "2026-10-01", "paid_at": None},
            }  # fmt: skip
            pricing["paid_usd"] = 2280
        trip.pricing = pricing
        # An imported roster sets the seat count (3, not 24).
        for name in ("Ana Ruiz", "Bea Cole", "Julia Pérez"):
            s.add(
                Traveler(tenant_id=tenant, trip_id=trip.id, full_name=name,
                         role=TravelerRole.PLAYER)
            )  # fmt: skip
        return trip.id


async def test_team_enrollment_reminder_end_to_end(engine: AsyncEngine) -> None:
    tenant = await _make_tenant(engine, "pay")
    other = await _make_tenant(engine, "pay-other")
    await _seed(engine, tenant, invoices=False)

    async with session_scope(tenant, engine=engine, role=APP_ROLE) as s:
        (pos,) = await payment_positions(s, tenant_id=tenant, today=TODAY)
    assert pos.plan.to is not None and pos.plan.to.name == "Dana Whitfield"
    assert [r.name for r in pos.plan.cc] == ["Robert Haines"]
    (line,) = pos.overdue
    assert (line.kind, line.seats, line.outstanding_usd) == (ItemKind.ENROLLMENT, 3, 285)
    assert line.stage is Stage.OVERDUE_7

    async with session_scope(tenant, engine=engine, role=APP_ROLE) as s:
        first = await queue_reminders(s, tenant_id=tenant, today=TODAY, llm=None)
    async with session_scope(tenant, engine=engine, role=APP_ROLE) as s:
        second = await queue_reminders(s, tenant_id=tenant, today=TODAY, llm=None)
    assert first["approvals_created"] == 1 and second["approvals_created"] == 0

    async with session_scope(tenant, engine=engine, role=APP_ROLE) as s:
        approval = (await s.scalars(select(Approval))).one()
        assert approval.status is ApprovalStatus.PENDING
        assert approval.proposed_action["action"] == "send_payment_reminder"
        params = approval.proposed_action["params"]
        assert params["to"]["email"] == "dana@lakeshore.example"
        assert params["cc"] == [{"name": "Robert Haines", "email": "rob@lakeshore.example"}]
        assert "3 travelers × US$95" in params["body"]
        assert not any(n in params["body"] for n in ("Ana", "Bea", "Julia"))
        # Nothing leaves until a person approves.
        assert await release_approved(s, tenant_id=tenant) == []
        approval.status = ApprovalStatus.APPROVED

    async with session_scope(tenant, engine=engine, role=APP_ROLE) as s:
        (event_id,) = await release_approved(s, tenant_id=tenant)
        assert await release_approved(s, tenant_id=tenant) == []
        event = await s.get(OutboxEvent, event_id)
        assert event is not None and event.type == SEND_EVENT
        assert event.payload["payloadHash"] == approval.payload_hash

    async with session_scope(other, engine=engine, role=APP_ROLE) as s:
        assert all(not p.lines for p in await payment_positions(s, tenant_id=other, today=TODAY))


async def test_imported_invoices_drive_the_position(engine: AsyncEngine) -> None:
    tenant = await _make_tenant(engine, "pay-inv")
    await _seed(engine, tenant, invoices=True)
    async with session_scope(tenant, engine=engine, role=APP_ROLE) as s:
        (pos,) = await payment_positions(s, tenant_id=tenant, today=TODAY)
    assert [(line.ref, line.stage) for line in pos.lines] == [
        ("INV-1043", Stage.OVERDUE_7),
        ("INV-1042", Stage.PAID),
    ]
    assert pos.overdue_usd == 12000


async def test_tampered_approval_is_not_released(engine: AsyncEngine) -> None:
    tenant = await _make_tenant(engine, "pay-tamper")
    await _seed(engine, tenant, invoices=False)
    async with session_scope(tenant, engine=engine, role=APP_ROLE) as s:
        await queue_reminders(s, tenant_id=tenant, today=TODAY, llm=None)
    async with session_scope(tenant, engine=engine, role=APP_ROLE) as s:
        approval = (await s.scalars(select(Approval))).one()
        action = dict(approval.proposed_action)
        action["params"] = {**action["params"], "body": "Wire US$9,999 to this account."}
        approval.proposed_action = action
        approval.status = ApprovalStatus.APPROVED
    async with session_scope(tenant, engine=engine, role=APP_ROLE) as s:
        assert await release_approved(s, tenant_id=tenant) == []
        approval = (await s.scalars(select(Approval))).one()
        assert approval.details["release_error"] == "payload hash mismatch"
