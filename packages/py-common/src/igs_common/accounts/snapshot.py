"""Load an `AccountSnapshot` from Postgres (the structured half of Account 360)."""

from __future__ import annotations

from datetime import UTC, date, datetime
from decimal import Decimal, InvalidOperation
from typing import Any
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from igs_common.db.models import Account, AccountFact, Interaction, Lead, Stakeholder, Trip
from igs_common.payments.position import TripPosition
from igs_common.payments.schedule import ops_today
from igs_common.payments.service import payment_positions

from .types import (
    AccountSnapshot,
    FactView,
    InteractionView,
    LeadView,
    StakeholderView,
    TripView,
)


async def load_snapshot(
    session: AsyncSession,
    *,
    tenant_id: UUID,
    account_id: UUID,
    interactions_limit: int = 12,
    today: date | None = None,
) -> AccountSnapshot | None:
    """Everything the brief/ask need, scoped to one tenant + account.

    RLS already scopes the session; the explicit `tenant_id` filter is defense in depth.
    """
    account = (
        await session.execute(
            select(Account).where(Account.id == account_id, Account.tenant_id == tenant_id)
        )
    ).scalar_one_or_none()
    if account is None:
        return None

    stakeholders = (
        (
            await session.execute(
                select(Stakeholder)
                .where(Stakeholder.account_id == account_id, Stakeholder.tenant_id == tenant_id)
                .order_by(Stakeholder.influence.desc(), Stakeholder.name)
            )
        )
        .scalars()
        .all()
    )
    names = {s.id: s.name for s in stakeholders}

    facts = (
        (
            await session.execute(
                select(AccountFact)
                .where(
                    AccountFact.account_id == account_id,
                    AccountFact.tenant_id == tenant_id,
                    AccountFact.superseded_by.is_(None),
                )
                .order_by(AccountFact.valid_from.desc())
            )
        )
        .scalars()
        .all()
    )

    recent = (
        (
            await session.execute(
                select(Interaction)
                .where(Interaction.account_id == account_id, Interaction.tenant_id == tenant_id)
                .order_by(Interaction.occurred_at.desc())
                .limit(interactions_limit)
            )
        )
        .scalars()
        .all()
    )
    recent_ids = {i.id for i in recent}
    missing = {f.source_interaction_id for f in facts} - recent_ids
    older: list[Interaction] = []
    if missing:
        older = list(
            (
                await session.execute(
                    select(Interaction)
                    .where(Interaction.id.in_(missing), Interaction.tenant_id == tenant_id)
                    .order_by(Interaction.occurred_at.desc())
                )
            )
            .scalars()
            .all()
        )

    trips = (
        (
            await session.execute(
                select(Trip)
                .where(Trip.account_id == account_id, Trip.tenant_id == tenant_id)
                .order_by(Trip.start_date)
            )
        )
        .scalars()
        .all()
    )
    leads = (
        (
            await session.execute(
                select(Lead)
                .where(Lead.account_id == account_id, Lead.tenant_id == tenant_id)
                .order_by(Lead.created_at.desc())
            )
        )
        .scalars()
        .all()
    )

    positions = {
        p.plan.trip_id: p
        for p in await payment_positions(
            session,
            tenant_id=tenant_id,
            today=today or ops_today(datetime.now(UTC)),
            account_id=account_id,
        )
    }

    location = ", ".join(p for p in (account.city, account.state, account.country) if p)
    return AccountSnapshot(
        tenant_id=tenant_id,
        account_id=account.id,
        name=account.name,
        kind=account.kind,
        status=account.status,
        stored_health=account.health,
        location=location,
        sport_programs=tuple(account.sport_programs or ()),
        stakeholders=tuple(
            StakeholderView(
                id=s.id,
                name=s.name,
                title=s.title,
                role=s.role,
                influence=s.influence,
                sentiment=s.sentiment,
                last_contact_at=s.last_contact_at,
            )
            for s in stakeholders
        ),
        facts=tuple(_fact_view(f) for f in facts),
        interactions=tuple(interaction_view(i, names) for i in recent),
        fact_sources=tuple(interaction_view(i, names) for i in older),
        trips=tuple(_trip_view(t, positions.get(t.id)) for t in trips),
        leads=tuple(
            LeadView(id=lead.id, status=lead.status, created_at=lead.created_at) for lead in leads
        ),
    )


def _fact_view(f: AccountFact) -> FactView:
    # severity / status / due_date are added by migration 0002; read them when present.
    return FactView(
        id=f.id,
        kind=f.kind,
        statement=f.statement,
        confidence=f.confidence,
        source_interaction_id=f.source_interaction_id,
        valid_from=f.valid_from,
        severity=_enum_value(getattr(f, "severity", None)),
        status=_enum_value(getattr(f, "status", None)),
        due_date=getattr(f, "due_date", None),
    )


def interaction_view(i: Interaction, names: dict[UUID, str]) -> InteractionView:
    return InteractionView(
        id=i.id,
        occurred_at=i.occurred_at,
        channel=i.channel,
        direction=i.direction,
        subject=i.subject,
        stakeholder_name=names.get(i.stakeholder_id) if i.stakeholder_id else None,
        body=i.body,
    )


def _trip_view(t: Trip, payments: TripPosition | None = None) -> TripView:
    pricing: dict[str, Any] = t.pricing or {}
    return TripView(
        id=t.id,
        code=t.code,
        title=t.title,
        status=t.status,
        start_date=t.start_date,
        end_date=t.end_date,
        total_usd=_decimal(pricing.get("total_usd")),
        paid_usd=_decimal(pricing.get("paid_usd")),
        payments=payments,
    )


def _decimal(value: object) -> Decimal | None:
    if value is None:
        return None
    try:
        return Decimal(str(value))
    except InvalidOperation:
        return None


def _enum_value(value: object) -> str | None:
    if value is None:
        return None
    return str(getattr(value, "value", value))
