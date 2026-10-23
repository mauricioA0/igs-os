"""Reminders enter the approvals inbox; only approved ones reach the outbox.

* ``enqueue_reminders`` creates one pending approval per ``ReminderGroup`` (action
  ``send_payment_reminder``, write-external, assigned to ops). The ``dedupe_key`` in
  ``details`` makes the daily scan idempotent: a reminder already proposed — pending, approved
  or rejected — is never proposed again. A rejection is respected, not retried.
* ``release_approved`` turns approved reminders into ``payment.reminder_send_requested`` outbox
  events, after re-checking the payload hash, so what is sent is exactly what a person approved
  (an "edit and approve" produces a new approval with its own hash). Each approval is released
  once (``details.released_event_id``).
"""

from __future__ import annotations

import uuid
from collections.abc import Sequence
from datetime import UTC, date, datetime, time
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from igs_common.db.enums import ActorType, ApprovalStatus, ToolClass, UserRole
from igs_common.db.models import Approval, AuditLog, OutboxEvent
from igs_common.domain.approvals import payload_hash, verify_payload
from igs_common.seed.anchor import OPS_TZ

from .reminders import ACTION, Draft, ReminderGroup, approval_title, usd

SEND_EVENT = "payment.reminder_send_requested"


def reminder_params(group: ReminderGroup, draft: Draft) -> dict[str, Any]:
    """The exact action a person approves (hashed into the approval)."""
    plan = group.position.plan
    return {
        "trip_id": str(plan.trip_id),
        "channel": "email",
        "to": {"name": plan.to.name, "email": plan.to.email} if plan.to else None,
        "cc": [{"name": r.name, "email": r.email} for r in plan.cc],
        "subject": draft.subject,
        "body": draft.body,
    }


def _details(group: ReminderGroup, draft: Draft) -> dict[str, Any]:
    plan = group.position.plan
    return {
        "dedupe_key": group.dedupe_key,
        "kind": "payment_reminder",
        "stage": group.stage.value,
        "as_of": group.today.isoformat(),
        "account": {
            "id": str(plan.account_id) if plan.account_id else None,
            "name": plan.account_name,
        },  # fmt: skip
        "trip": {"id": str(plan.trip_id), "code": plan.code, "title": plan.title},
        "total_outstanding_usd": group.total_usd,
        "seats": group.seats,
        "lines": [
            {
                "kind": line.kind.value,
                "due": line.due.isoformat(),
                "amount_usd": line.amount_usd,
                "seats": line.seats,
                "outstanding_usd": line.outstanding_usd,
                "stage": line.stage.value,
                "days": line.days,
                "ref": line.ref,
            }
            for line in group.lines
        ],
        "draft": {"source": draft.source, "problems": list(draft.problems)},
        "reason": f"{usd(group.total_usd)} {group.stage.value.replace('_', ' ')} "
        f"según el plan de pagos de IGS",
        "missing_recipient": plan.to is None or not plan.to.email,
    }


async def existing_keys(session: AsyncSession, keys: Sequence[str]) -> set[str]:
    if not keys:
        return set()
    rows = await session.scalars(
        select(Approval.details["dedupe_key"].astext).where(
            Approval.details["dedupe_key"].astext.in_(list(keys))
        )
    )
    return {k for k in rows.all() if k}


async def enqueue_reminders(
    session: AsyncSession,
    *,
    tenant_id: uuid.UUID,
    drafts: Sequence[tuple[ReminderGroup, Draft]],
    actor_id: str = "payments.reminders",
) -> list[uuid.UUID]:
    """Create the approvals that don't exist yet; returns the new approval ids."""
    seen = await existing_keys(session, [g.dedupe_key for g, _ in drafts])
    created: list[uuid.UUID] = []
    for group, draft in drafts:
        if group.dedupe_key in seen:
            continue
        seen.add(group.dedupe_key)
        params = reminder_params(group, draft)
        approval = Approval(
            id=uuid.uuid5(uuid.NAMESPACE_URL, f"igs:{tenant_id}:{group.dedupe_key}"),
            tenant_id=tenant_id,
            subject_type="trip",
            subject_id=group.position.plan.trip_id,
            title=approval_title(group),
            details=_details(group, draft),
            proposed_action={"action": ACTION, "params": params},
            payload_hash=payload_hash(ACTION, params),
            risk_class=ToolClass.EXTERNAL,
            assignee_role=UserRole.OPS,
            status=ApprovalStatus.PENDING,
            expires_at=_end_of_ops_day(group.expires_on),
        )
        session.add(approval)
        session.add(
            AuditLog(
                tenant_id=tenant_id,
                actor_type=ActorType.SYSTEM,
                actor_id=actor_id,
                action="approval.request",
                subject_type="approval",
                subject_id=approval.id,
                after={"action": ACTION, "payload_hash": approval.payload_hash},
            )
        )
        created.append(approval.id)
    await session.flush()
    return created


async def release_approved(session: AsyncSession, *, tenant_id: uuid.UUID) -> list[uuid.UUID]:
    """Outbox events for approved, not yet released reminders; returns the event ids."""
    rows = await session.scalars(
        select(Approval)
        .where(
            Approval.tenant_id == tenant_id,
            Approval.status == ApprovalStatus.APPROVED,
            Approval.proposed_action["action"].astext == ACTION,
            Approval.details["released_event_id"].astext.is_(None),
        )
        .with_for_update(skip_locked=True)
    )
    events: list[uuid.UUID] = []
    for approval in rows.all():
        params = (approval.proposed_action or {}).get("params") or {}
        if not verify_payload(approval.payload_hash, ACTION, params):
            approval.details = {**approval.details, "release_error": "payload hash mismatch"}
            continue
        if not (params.get("to") or {}).get("email"):
            approval.details = {**approval.details, "release_error": "no recipient email"}
            continue
        event_id = uuid.uuid5(uuid.NAMESPACE_URL, f"igs:event:{SEND_EVENT}:{approval.id}")
        session.add(
            OutboxEvent(
                id=event_id,
                tenant_id=tenant_id,
                type=SEND_EVENT,
                subject_type="trip",
                subject_id=uuid.UUID(params["trip_id"]),
                payload={
                    **params,
                    "approvalId": str(approval.id),
                    "payloadHash": approval.payload_hash,
                    "idempotencyKey": f"approval:{approval.id}",
                },
            )
        )
        approval.details = {**approval.details, "released_event_id": str(event_id)}
        events.append(event_id)
    await session.flush()
    return events


def _end_of_ops_day(d: date) -> datetime:
    return datetime.combine(d, time(23, 59), tzinfo=OPS_TZ).astimezone(UTC)
