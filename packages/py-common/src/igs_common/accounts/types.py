"""Read models for Account 360: an exact, SQL-derived snapshot the AI features reason over."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime
from decimal import Decimal
from typing import TYPE_CHECKING
from uuid import UUID

from igs_common.db.enums import (
    AccountHealth,
    AccountKind,
    AccountStatus,
    Direction,
    FactKind,
    InteractionChannel,
    LeadStatus,
    Sentiment,
    StakeholderRole,
    TripStatus,
)

if TYPE_CHECKING:
    from igs_common.payments.position import TripPosition


@dataclass(frozen=True)
class StakeholderView:
    id: UUID
    name: str
    title: str | None
    role: StakeholderRole
    influence: int
    sentiment: Sentiment
    last_contact_at: datetime | None


@dataclass(frozen=True)
class FactView:
    """A current (not superseded) fact. severity/status/due_date arrive with migration 0002."""

    id: UUID
    kind: FactKind
    statement: str
    confidence: float
    source_interaction_id: UUID
    valid_from: datetime
    severity: str | None = None  # low | medium | high (risks)
    status: str | None = None  # open | done | dropped; None = open
    due_date: date | None = None  # commitments

    @property
    def is_open(self) -> bool:
        return self.status in (None, "open")


@dataclass(frozen=True)
class InteractionView:
    id: UUID
    occurred_at: datetime
    channel: InteractionChannel
    direction: Direction
    subject: str | None
    stakeholder_name: str | None
    body: str


@dataclass(frozen=True)
class TripView:
    id: UUID
    code: str | None
    title: str
    status: TripStatus
    start_date: date
    end_date: date
    total_usd: Decimal | None
    paid_usd: Decimal | None
    # Per-traveler schedule under IGS's terms (igs_common.payments), when the trip has one.
    payments: TripPosition | None = None

    @property
    def balance_usd(self) -> Decimal | None:
        if self.total_usd is None:
            return None
        return self.total_usd - (self.paid_usd or Decimal(0))


@dataclass(frozen=True)
class LeadView:
    id: UUID
    status: LeadStatus
    created_at: datetime


@dataclass(frozen=True)
class AccountSnapshot:
    tenant_id: UUID
    account_id: UUID
    name: str
    kind: AccountKind
    status: AccountStatus
    stored_health: AccountHealth
    location: str
    sport_programs: tuple[str, ...]
    stakeholders: tuple[StakeholderView, ...] = ()
    facts: tuple[FactView, ...] = ()
    interactions: tuple[InteractionView, ...] = ()  # newest first, bounded
    trips: tuple[TripView, ...] = ()
    leads: tuple[LeadView, ...] = ()
    # Interactions referenced by facts but older than the bounded `interactions` window.
    fact_sources: tuple[InteractionView, ...] = field(default=())

    def interaction(self, interaction_id: UUID) -> InteractionView | None:
        for item in (*self.interactions, *self.fact_sources):
            if item.id == interaction_id:
                return item
        return None


@dataclass(frozen=True)
class HealthResult:
    health: AccountHealth
    reasons: tuple[str, ...]  # Spanish, shown in the ops UI next to the health dot


@dataclass(frozen=True)
class Citation:
    """`[n]` in a generated text. `interaction_id` is None for the system record (SQL state)."""

    n: int
    interaction_id: UUID | None
    label: str


class AccountNotFoundError(LookupError):
    pass
