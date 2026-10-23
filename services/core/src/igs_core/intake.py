"""Lead intake: one inbound inquiry → contact, maybe a lead, a score, a reply to approve, a clock.

``receive`` is the whole pipeline, in one tenant transaction:

1. **Idempotency.** The same form submission or email (Message-ID) returns the intake it already
   created.
2. **Spam.** The site's honeypot (``website``) is recorded as ``spam``: no contact, no reply.
3. **Who is it.** The contact by email; the account from the contact, the program name or a
   colleague on the same institutional domain. A trip that went ahead makes it a returning
   customer; "Referral / Word of Mouth" a referral.
4. **Follow-ups merge.** A new message from a contact with an open intake fills that intake's
   gaps (never erases what they already said) and restarts the response clock.
5. **Extract** (``igs_common.intake.extract``): model with verbatim evidence, rules as fallback.
6. **Lead** only when every field the lead model requires is known; otherwise the intake stays
   ``open`` and the reply asks for what's missing.
7. **Score** with reasons, **draft reply** (``send_email`` approval for ops, with call times) and
   the **1-business-day** due time, which the Hoy queue sorts by.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from typing import Any
from uuid import UUID

import structlog
from sqlalchemy import func, or_, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from igs_common.db.base import uuid7
from igs_common.db.enums import ApprovalStatus, ToolClass, TripStatus, UserRole
from igs_common.db.models import Account, Approval, Contact, Lead, LeadIntake, Trip
from igs_common.domain.approvals import payload_hash
from igs_common.intake import (
    LEAD_REQUIRED,
    BusinessCalendar,
    Extraction,
    Reason,
    draft_reply,
    extract,
    parse_window,
    score_inquiry,
)
from igs_common.intake.score import FREE_MAIL
from igs_common.llm import LLMClient
from igs_core.events import audit, emit
from igs_core.repositories import Principal

log = structlog.get_logger("igs_core.intake")

REPLY_ACTION = "send_email"
# A message from the same contact within this window continues their open intake.
FOLLOW_UP_WINDOW = timedelta(days=60)
TRAVELED = (TripStatus.CONFIRMED, TripStatus.IN_PROGRESS, TripStatus.COMPLETED)


@dataclass(frozen=True)
class Inquiry:
    """One inbound message, whatever the channel, in the shape the pipeline needs."""

    channel: str  # form | email
    dedupe_key: str
    first_name: str
    full_name: str
    email: str
    program: str
    source_text: str
    submitted: dict[str, Any]
    received_at: datetime
    role: str | None = None
    how_heard: str | None = None
    phone: str | None = None
    travel_window: str = ""
    subject: str | None = None  # email subject, for "Re: …"
    spam: bool = False


@dataclass(frozen=True)
class Received:
    intake: LeadIntake
    created: bool  # False: an exact resubmission, nothing new happened
    merged: bool = False


async def receive(
    session: AsyncSession,
    tenant_id: UUID,
    inquiry: Inquiry,
    *,
    llm: LLMClient | None,
    calendar: BusinessCalendar,
    request_id: str | None = None,
    now: datetime | None = None,
) -> Received:
    now = now or datetime.now(UTC)
    actor = Principal(
        kind="demo", tenant_id=tenant_id, role="viewer", subject=f"intake:{inquiry.channel}"
    )
    seen = await session.scalar(
        select(LeadIntake).where(
            or_(
                LeadIntake.dedupe_key == inquiry.dedupe_key,
                LeadIntake.submitted["message_keys"].contains([inquiry.dedupe_key]),
            )
        )
    )
    if seen is not None:
        return Received(intake=seen, created=False)

    if inquiry.spam:
        intake = LeadIntake(
            id=uuid7(),
            tenant_id=tenant_id,
            channel=inquiry.channel,
            status="spam",
            dedupe_key=inquiry.dedupe_key,
            submitted=inquiry.submitted,
            body_text=inquiry.source_text,
            received_at=inquiry.received_at,
            sla_due_at=inquiry.received_at,
        )
        session.add(intake)
        await session.flush()
        log.info("intake_spam", intake_id=str(intake.id), channel=inquiry.channel)
        return Received(intake=intake, created=True)

    contact = await session.scalar(
        select(Contact)
        .where(func.lower(Contact.email) == inquiry.email.lower())
        .order_by(Contact.created_at)
        .limit(1)
    )
    account_id = contact.account_id if contact is not None else None
    if account_id is None:
        account_id = await _account_for(session, inquiry)
    relationship, notes = await _relationship(session, inquiry, contact, account_id)

    extraction = await extract(llm, inquiry.source_text)
    open_intake = await _open_intake(session, inquiry.email, now) if contact is not None else None

    if contact is None:
        contact = Contact(
            id=uuid7(),
            tenant_id=tenant_id,
            name=inquiry.full_name or inquiry.email,
            email=inquiry.email,
            phone=inquiry.phone or None,
            organization=inquiry.program or None,
            role=inquiry.role,
            account_id=account_id,
        )
        session.add(contact)
        await session.flush()
    else:
        contact.phone = contact.phone or inquiry.phone or None
        contact.organization = contact.organization or inquiry.program or None
        contact.role = contact.role or inquiry.role
        contact.account_id = contact.account_id or account_id

    merged = open_intake is not None
    if open_intake is not None:
        intake = open_intake
        previous = dict((intake.extracted or {}).get("values") or {})
        values = extraction.merged_over(_parse_values(previous))
        evidence = {**(intake.extracted or {}).get("evidence", {}), **extraction.evidence}
        keys = list((intake.submitted or {}).get("message_keys") or [])
        intake.submitted = {
            **(intake.submitted or {}),
            "message_keys": [*keys, inquiry.dedupe_key],
            "follow_ups": [*(intake.submitted or {}).get("follow_ups", []), inquiry.submitted],
        }
        intake.body_text = f"{intake.body_text}\n\n---\n\n{inquiry.source_text}"
        # The coach wrote again: the promise to answer within a business day starts over.
        intake.received_at = inquiry.received_at
        intake.first_response_at = None
    else:
        values = dict(extraction.values)
        evidence = dict(extraction.evidence)
        intake = LeadIntake(
            id=uuid7(),
            tenant_id=tenant_id,
            channel=inquiry.channel,
            status="open",
            dedupe_key=inquiry.dedupe_key,
            submitted={**inquiry.submitted, "message_keys": [inquiry.dedupe_key]},
            body_text=inquiry.source_text,
            received_at=inquiry.received_at,
            sla_due_at=calendar.due(inquiry.received_at),
        )
        session.add(intake)
    intake.contact_id = contact.id
    intake.account_id = intake.account_id or account_id
    intake.relationship = relationship
    intake.sla_due_at = calendar.due(inquiry.received_at)
    missing = [name for name in LEAD_REQUIRED if values.get(name) is None]
    intake.missing = missing
    intake.extracted = Extraction(
        values=values,
        evidence=evidence,
        rejected=extraction.rejected,
        method=extraction.method,
        model=extraction.model,
    ).to_json()
    intake.extraction_model = extraction.model or extraction.method
    await session.flush()

    lead: Lead | None = None
    if not missing and intake.lead_id is None:
        lead = _lead(tenant_id, values, contact, account_id)
        session.add(lead)
        await session.flush()
        intake.lead_id = lead.id
        intake.status = "lead_created"

    score = score_inquiry(
        values=values,
        relationship=relationship,
        role=inquiry.role,
        email=inquiry.email,
        travel_window=parse_window(inquiry.travel_window),
        today=now.astimezone(calendar.zone).date(),
        missing=missing,
        notes=notes,
    )
    intake.score = score.value
    intake.score_reasons = score.to_json()

    reply = draft_reply(
        first_name=inquiry.first_name,
        email=inquiry.email,
        program=inquiry.program or contact.organization or "your program",
        values=values,
        missing=missing,
        relationship=relationship,
        call_slots=calendar.call_slots(now),
        slot_tz=calendar.tz,
        in_reply_to_subject=inquiry.subject,
    )
    approval = await _reply_approval(session, intake, reply, inquiry, score.value)
    intake.approval_id = approval.id
    await session.flush()

    await audit(
        session,
        actor,
        action="intake.merged" if merged else "intake.received",
        subject_type="lead_intake",
        subject_id=intake.id,
        after={
            "channel": inquiry.channel,
            "relationship": relationship,
            "score": score.value,
            "missing": missing,
            "lead_id": str(intake.lead_id) if intake.lead_id else None,
            "approval_id": str(approval.id),
        },
        request_id=request_id,
    )
    await emit(
        session,
        tenant_id=tenant_id,
        type="intake.received",
        subject_type="lead_intake",
        subject_id=intake.id,
        payload={
            "channel": inquiry.channel,
            "score": score.value,
            "relationship": relationship,
            "slaDueAt": intake.sla_due_at.isoformat(),
            "approvalId": str(approval.id),
            "merged": merged,
        },
    )
    if lead is not None:
        await emit(
            session,
            tenant_id=tenant_id,
            type="lead.created",
            subject_type="lead",
            subject_id=lead.id,
            payload={"source": inquiry.channel, "intakeId": str(intake.id)},
        )
    log.info(
        "intake_received",
        intake_id=str(intake.id),
        channel=inquiry.channel,
        score=score.value,
        missing=len(missing),
        merged=merged,
        method=extraction.method,
    )
    return Received(intake=intake, created=True, merged=merged)


async def mark_responded(session: AsyncSession, approval: Approval, when: datetime) -> UUID | None:
    """An approved first reply stops the intake's clock. Returns the intake id, if any."""
    raw = (approval.details or {}).get("intake_id")
    if not raw:
        return None
    try:
        intake_id = UUID(str(raw))
    except ValueError:
        return None
    await session.execute(
        update(LeadIntake)
        .where(LeadIntake.id == intake_id, LeadIntake.first_response_at.is_(None))
        .values(first_response_at=when)
    )
    return intake_id


# ── Steps ─────────────────────────────────────────────────────────────────────


async def _account_for(session: AsyncSession, inquiry: Inquiry) -> UUID | None:
    if inquiry.program:
        by_name = await session.scalar(
            select(Account.id).where(func.lower(Account.name) == inquiry.program.strip().lower())
        )
        if by_name is not None:
            return by_name
    domain = inquiry.email.rsplit("@", 1)[-1].lower()
    if not domain or domain in FREE_MAIL:
        return None
    return await session.scalar(
        select(Contact.account_id)
        .where(Contact.account_id.is_not(None), func.lower(Contact.email).like(f"%@{domain}"))
        .limit(1)
    )


async def _relationship(
    session: AsyncSession, inquiry: Inquiry, contact: Contact | None, account_id: UUID | None
) -> tuple[str, list[Reason]]:
    notes: list[Reason] = []
    traveled = False
    if account_id is not None:
        traveled = (
            await session.scalar(
                select(func.count())
                .select_from(Trip)
                .where(Trip.account_id == account_id, Trip.status.in_(TRAVELED))
            )
            or 0
        ) > 0
    claims_returning = inquiry.how_heard == "Returning Customer"
    if traveled:
        return "returning_customer", notes
    if claims_returning:
        notes.append(
            Reason(0, "Dice ser cliente recurrente pero no hay un viaje suyo registrado: verificar")
        )
    if (inquiry.how_heard or "").startswith("Referral"):
        return "referral", notes
    if contact is not None or account_id is not None:
        return "known_contact", notes
    return "new", notes


async def _open_intake(session: AsyncSession, email: str, now: datetime) -> LeadIntake | None:
    return await session.scalar(
        select(LeadIntake)
        .join(Contact, Contact.id == LeadIntake.contact_id)
        .where(
            func.lower(Contact.email) == email.lower(),
            LeadIntake.status == "open",
            LeadIntake.created_at >= now - FOLLOW_UP_WINDOW,
        )
        .order_by(LeadIntake.created_at.desc())
        .limit(1)
        .with_for_update(of=LeadIntake)
    )


def _lead(
    tenant_id: UUID, values: dict[str, Any], contact: Contact, account_id: UUID | None
) -> Lead:
    return Lead(
        id=uuid7(),
        tenant_id=tenant_id,
        contact_id=contact.id,
        account_id=account_id,
        sport=values["sport"],
        gender=values["gender"],
        age_group=str(values["age_group"]),
        level_score=int(values["level_score"]),
        group_size=int(values["group_size"]),
        destination_country=str(values["destination_country"]),
        travel_start=values["travel_start"],
        duration_days=int(values["duration_days"]),
        budget_per_person_usd=values.get("budget_per_person_usd"),
        goals=values.get("goals"),
        status="new",
        source="webhook",
    )


async def _reply_approval(
    session: AsyncSession, intake: LeadIntake, reply: Any, inquiry: Inquiry, score: int
) -> Approval:
    # A follow-up replaces the reply nobody approved yet: one pending reply per intake.
    pending = (
        await session.scalars(
            select(Approval).where(
                Approval.subject_type == "lead_intake",
                Approval.subject_id == intake.id,
                Approval.status == ApprovalStatus.PENDING,
            )
        )
    ).all()
    params = reply.action_params()
    who = inquiry.full_name or inquiry.email
    approval = Approval(
        id=uuid7(),
        tenant_id=intake.tenant_id,
        subject_type="lead_intake",
        subject_id=intake.id,
        title=f"Responder a {who} · {inquiry.program or 'consulta'}",
        details={
            "summary": _summary(intake, inquiry, score),
            "source": f"intake.{inquiry.channel}",
            "intake_id": str(intake.id),
            "score": score,
            "score_reasons": intake.score_reasons,
            "missing": list(intake.missing),
            "relationship": intake.relationship,
            "sla_due_at": intake.sla_due_at.isoformat(),
            "call_slots": [s.isoformat() for s in reply.call_slots],
            "lead_id": str(intake.lead_id) if intake.lead_id else None,
        },
        proposed_action={"action": REPLY_ACTION, "params": params},
        payload_hash=payload_hash(REPLY_ACTION, params),
        risk_class=ToolClass.EXTERNAL,
        assignee_role=UserRole.OPS,
    )
    session.add(approval)
    await session.flush()
    for old in pending:
        old.status = ApprovalStatus.SUPERSEDED
        old.superseded_by = approval.id
    return approval


def _summary(intake: LeadIntake, inquiry: Inquiry, score: int) -> str:
    kind = {
        "returning_customer": "Cliente recurrente",
        "referral": "Referido",
        "known_contact": "Contacto conocido",
        "new": "Consulta nueva",
    }[intake.relationship]
    via = "el formulario del sitio" if inquiry.channel == "form" else "mail"
    gaps = len(intake.missing)
    tail = (
        "Ya tiene todo para cotizar: el lead está creado."
        if not gaps
        else f"Faltan {gaps} datos para cotizar; la respuesta los pregunta."
    )
    return f"{kind} por {via}, puntaje {score}/100. {tail}"


def _parse_values(values: dict[str, Any]) -> dict[str, Any]:
    out = dict(values)
    raw = out.get("travel_start")
    if isinstance(raw, str):
        try:
            out["travel_start"] = date.fromisoformat(raw)
        except ValueError:
            out["travel_start"] = None
    return out
