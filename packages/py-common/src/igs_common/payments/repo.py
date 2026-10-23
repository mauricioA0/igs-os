"""Load ``TripPlan``s from Postgres for one tenant (RLS-scoped session).

Reads the trip ledger the importer writes (``pricing.payments`` / ``pricing.paid_usd``) and the
team-level ``pricing.payment_terms``; see ``position`` for the rules. Seats are the imported
roster size when there is one.

Reminders go to adults only: the lead's contact (the coach who booked), with the client's
athletic director / decision maker / finance contact in copy. Minors never have an email
(``travelers.minor_no_contact``) and are never recipients.
"""

from __future__ import annotations

from collections import defaultdict
from datetime import date
from typing import Any
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from igs_common.db.enums import StakeholderRole, TripStatus
from igs_common.db.models import Account, Contact, Lead, Stakeholder, Traveler, Trip

from .position import Invoice, Recipient, TripPlan
from .schedule import Plan

_LIVE = (TripStatus.PROPOSED, TripStatus.CONFIRMED, TripStatus.IN_PROGRESS)
_CC_ROLES = (
    StakeholderRole.ATHLETIC_DIRECTOR,
    StakeholderRole.DECISION_MAKER,
    StakeholderRole.FINANCE,
)
_TO_ROLES = (StakeholderRole.COACH, StakeholderRole.CHAMPION, StakeholderRole.TRAVEL_COORDINATOR)


def _date(value: Any) -> date | None:
    if not value:
        return None
    try:
        return date.fromisoformat(str(value)[:10])
    except ValueError:
        return None


def _invoices(raw: Any) -> tuple[Invoice, ...]:
    if not isinstance(raw, dict):
        return ()
    out: list[Invoice] = []
    for ref, entry in sorted(raw.items()):
        if not isinstance(entry, dict):
            continue
        due = _date(entry.get("due_date"))
        amount = entry.get("amount_usd")
        if due is None or not isinstance(amount, int | float) or amount <= 0:
            continue  # the importer validates; a hand-edited row is skipped, not guessed
        out.append(
            Invoice(
                ref=str(ref),
                kind=str(entry.get("kind") or "other"),
                amount_usd=int(amount),
                due=due,
                paid_on=_date(entry.get("paid_at")),
            )
        )
    return tuple(out)


async def load_trip_plans(
    session: AsyncSession,
    *,
    tenant_id: UUID,
    today: date,
    account_id: UUID | None = None,
    trip_id: UUID | None = None,
) -> list[TripPlan]:
    q = select(Trip).where(
        Trip.tenant_id == tenant_id, Trip.status.in_(_LIVE), Trip.end_date >= today
    )
    if account_id is not None:
        q = q.where(Trip.account_id == account_id)
    if trip_id is not None:
        q = q.where(Trip.id == trip_id)
    trips = list((await session.scalars(q.order_by(Trip.start_date))).all())
    if not trips:
        return []

    roster: dict[UUID, int] = {
        tid: int(n)
        for tid, n in (
            await session.execute(
                select(Traveler.trip_id, func.count())
                .where(Traveler.tenant_id == tenant_id, Traveler.trip_id.in_([t.id for t in trips]))
                .group_by(Traveler.trip_id)
            )
        ).all()
    }
    account_ids = {t.account_id for t in trips if t.account_id}
    accounts = {
        a.id: a
        for a in (await session.scalars(select(Account).where(Account.id.in_(account_ids)))).all()
    }
    people: dict[UUID, list[Stakeholder]] = defaultdict(list)
    for s in (
        await session.scalars(
            select(Stakeholder)
            .where(Stakeholder.account_id.in_(account_ids))
            .order_by(Stakeholder.influence.desc(), Stakeholder.name)
        )
    ).all():
        people[s.account_id].append(s)
    lead_contacts: dict[UUID, Contact] = {
        lead_id: contact
        for lead_id, contact in (
            await session.execute(
                select(Lead.id, Contact)
                .join(Contact, Contact.id == Lead.contact_id)
                .where(Lead.id.in_({t.lead_id for t in trips if t.lead_id}))
            )
        ).all()
    }

    plans: list[TripPlan] = []
    for t in trips:
        pricing: dict[str, Any] = t.pricing or {}
        terms: dict[str, Any] = pricing.get("payment_terms") or {}
        to, cc = _recipients(
            lead_contacts.get(t.lead_id) if t.lead_id else None,
            people[t.account_id] if t.account_id else [],
        )
        account = accounts.get(t.account_id) if t.account_id else None
        plans.append(
            TripPlan(
                trip_id=t.id,
                code=t.code,
                title=t.title,
                status=t.status.value,
                start_date=t.start_date,
                price_per_person_usd=t.price_per_person_usd,
                travelers=roster.get(t.id) or t.travelers,
                account_id=t.account_id,
                account_name=account.name if account else None,
                to=to,
                cc=cc,
                invoices=_invoices(pricing.get("payments")),
                paid_usd=int(pricing.get("paid_usd") or 0),
                enrollment_due=_date(terms.get("enrollment_due")),
                group_enrolled_on=_date(terms.get("group_enrolled_on")),
                group_plan=Plan(terms.get("group_plan") or "manual"),
                balance_due_override=_date(terms.get("balance_due_override")),
            )
        )
    return plans


def _recipients(
    contact: Contact | None, people: list[Stakeholder]
) -> tuple[Recipient | None, tuple[Recipient, ...]]:
    to: Recipient | None = None
    if contact is not None:
        to = Recipient(contact.name, contact.email, contact.role or "coach")
    else:
        lead_person = next((p for p in people if p.role in _TO_ROLES and p.email), None)
        if lead_person is not None:
            to = Recipient(lead_person.name, lead_person.email, lead_person.role.value)
    taken = {to.email.lower()} if to and to.email else set()
    cc: list[Recipient] = []
    for p in people:
        if p.role in _CC_ROLES and p.email and p.email.lower() not in taken:
            cc.append(Recipient(p.name, p.email, p.role.value))
            taken.add(p.email.lower())
    return to, tuple(cc[:2])
