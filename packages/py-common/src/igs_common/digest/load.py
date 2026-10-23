"""SQL → `DigestInputs`, scoped to one tenant (RLS session + explicit filters).

Reads the same records the Hoy screen does: live trips with their items, effectively pending
approvals, account snapshots (health is recomputed by the same rules), open incidents and
unanswered leads.
"""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal, InvalidOperation
from uuid import UUID

from sqlalchemy import and_, exists, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from igs_common.accounts.snapshot import load_snapshot
from igs_common.accounts.types import AccountSnapshot
from igs_common.db.enums import (
    AccountStatus,
    ApprovalStatus,
    Direction,
    IncidentStatus,
    InteractionChannel,
    ItemStatus,
    LeadStatus,
    TripStatus,
)
from igs_common.db.models import (
    Account,
    Approval,
    Contact,
    Incident,
    Interaction,
    Lead,
    Trip,
    TripItem,
)

from .types import ApprovalInput, DigestInputs, IncidentInput, LeadInput, TripInput

_LIVE = (TripStatus.PROPOSED, TripStatus.CONFIRMED, TripStatus.IN_PROGRESS)
_OPEN_ITEMS = (ItemStatus.PENDING, ItemStatus.REQUESTED)


async def load_digest_inputs(
    session: AsyncSession, *, tenant_id: UUID, now: datetime
) -> DigestInputs:
    return DigestInputs(
        accounts=await _accounts(session, tenant_id),
        trips=await _trips(session, tenant_id),
        approvals=await _approvals(session, tenant_id, now),
        leads=await _leads(session, tenant_id),
        incidents=await _incidents(session, tenant_id),
    )


async def _accounts(session: AsyncSession, tenant_id: UUID) -> tuple[AccountSnapshot, ...]:
    ids = (
        await session.scalars(
            select(Account.id)
            .where(
                Account.tenant_id == tenant_id,
                Account.status.in_((AccountStatus.ACTIVE, AccountStatus.PROSPECT)),
            )
            .order_by(Account.name)
        )
    ).all()
    snapshots = []
    for account_id in ids:
        snap = await load_snapshot(
            session, tenant_id=tenant_id, account_id=account_id, interactions_limit=0
        )
        if snap is not None:
            snapshots.append(snap)
    return tuple(snapshots)


async def _trips(session: AsyncSession, tenant_id: UUID) -> tuple[TripInput, ...]:
    open_items = (
        select(func.count())
        .select_from(TripItem)
        .where(
            TripItem.tenant_id == tenant_id,
            TripItem.trip_id == Trip.id,
            TripItem.status.in_(_OPEN_ITEMS),
        )
        .scalar_subquery()
    )
    rows = (
        await session.execute(
            select(Trip, Account.name, open_items)
            .outerjoin(Account, and_(Account.id == Trip.account_id, Account.tenant_id == tenant_id))
            .where(Trip.tenant_id == tenant_id, Trip.status.in_(_LIVE))
            .order_by(Trip.start_date, Trip.id)
        )
    ).all()
    out = []
    for trip, account_name, open_count in rows:
        pricing = trip.pricing or {}
        out.append(
            TripInput(
                id=trip.id,
                code=trip.code,
                title=trip.title,
                account_id=trip.account_id,
                account_name=account_name,
                status=trip.status.value,
                start_date=trip.start_date,
                end_date=trip.end_date,
                travelers=trip.travelers,
                total_usd=_decimal(pricing.get("total_usd")),
                paid_usd=_decimal(pricing.get("paid_usd")),
                open_items=int(open_count or 0),
            )
        )
    return tuple(out)


async def _approvals(
    session: AsyncSession, tenant_id: UUID, now: datetime
) -> tuple[ApprovalInput, ...]:
    # Same rule as the inbox: pending and not past its expiry.
    rows = (
        await session.scalars(
            select(Approval)
            .where(
                Approval.tenant_id == tenant_id,
                Approval.status == ApprovalStatus.PENDING,
                or_(Approval.expires_at.is_(None), Approval.expires_at > now),
            )
            .order_by(Approval.created_at, Approval.id)
        )
    ).all()
    return tuple(
        ApprovalInput(
            id=a.id,
            title=a.title,
            created_at=a.created_at,
            expires_at=a.expires_at,
            subject_type=a.subject_type,
            subject_id=a.subject_id,
        )
        for a in rows
    )


async def _leads(session: AsyncSession, tenant_id: UUID) -> tuple[LeadInput, ...]:
    # Answered = a person wrote back on this lead. The web chat's own replies don't count.
    answered = exists().where(
        Interaction.tenant_id == tenant_id,
        Interaction.lead_id == Lead.id,
        Interaction.direction == Direction.OUTBOUND,
        Interaction.channel != InteractionChannel.CHAT,
    )
    rows = (
        await session.execute(
            select(Lead, Contact.organization, Contact.name, answered.label("answered"))
            .outerjoin(Contact, and_(Contact.id == Lead.contact_id, Contact.tenant_id == tenant_id))
            .where(
                Lead.tenant_id == tenant_id,
                Lead.status.in_((LeadStatus.NEW, LeadStatus.QUALIFIED)),
            )
            .order_by(Lead.created_at, Lead.id)
        )
    ).all()
    return tuple(
        LeadInput(
            id=lead.id,
            status=lead.status.value,
            created_at=lead.created_at,
            organization=organization,
            contact_name=contact_name,
            sport=lead.sport.value,
            group_size=lead.group_size,
            answered=bool(was_answered),
        )
        for lead, organization, contact_name, was_answered in rows
    )


async def _incidents(session: AsyncSession, tenant_id: UUID) -> tuple[IncidentInput, ...]:
    rows = (
        await session.execute(
            select(Incident, Trip.code)
            .join(Trip, and_(Trip.id == Incident.trip_id, Trip.tenant_id == tenant_id))
            .where(Incident.tenant_id == tenant_id, Incident.status != IncidentStatus.RESOLVED)
            .order_by(Incident.occurred_at)
        )
    ).all()
    return tuple(
        IncidentInput(
            id=inc.id,
            trip_id=inc.trip_id,
            trip_code=code,
            severity=inc.severity.value,
            title=inc.title,
            occurred_at=inc.occurred_at,
        )
        for inc, code in rows
    )


def _decimal(value: object) -> Decimal | None:
    if value is None:
        return None
    try:
        return Decimal(str(value))
    except InvalidOperation:
        return None
