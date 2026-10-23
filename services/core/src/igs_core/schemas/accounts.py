from datetime import date, datetime
from typing import Literal
from uuid import UUID

from igs_core.schemas.common import Schema

AccountKind = Literal["university", "club", "high_school", "family_group"]
AccountStatus = Literal["prospect", "active", "past", "churned"]
Health = Literal["green", "amber", "red"]
StakeholderRole = Literal[
    "decision_maker",
    "champion",
    "coach",
    "assistant_coach",
    "athletic_director",
    "compliance",
    "travel_coordinator",
    "finance",
    "parent_liaison",
    "other",
]
Sentiment = Literal["positive", "neutral", "negative", "unknown"]
FactKind = Literal["status", "commitment", "risk", "preference", "budget", "decision"]


class AccountSummary(Schema):
    id: UUID
    name: str
    kind: AccountKind
    country: str
    state: str | None = None
    city: str | None = None
    sport_programs: list[str] = []
    tier: str | None = None
    status: AccountStatus
    health: Health
    created_at: datetime


class Stakeholder(Schema):
    id: UUID
    name: str
    title: str | None = None
    role: StakeholderRole
    influence: int
    sentiment: Sentiment
    email: str | None = None
    phone: str | None = None
    preferred_channel: str | None = None
    last_contact_at: datetime | None = None
    notes: str | None = None


class AccountFact(Schema):
    id: UUID
    kind: FactKind
    statement: str
    confidence: float
    source_interaction_id: UUID
    valid_from: date | datetime | None = None


class InteractionSummary(Schema):
    id: UUID
    channel: str
    direction: str | None = None
    occurred_at: datetime
    subject: str | None = None
    stakeholder_id: UUID | None = None
    trip_id: UUID | None = None
    lead_id: UUID | None = None
    # First ~280 characters of the body, whitespace collapsed (citation previews).
    excerpt: str | None = None


class AccountDetail(AccountSummary):
    # Deterministic health rules (igs_common.accounts.health), Spanish; never from the model.
    health_reasons: list[str] = []
    stakeholders: list[Stakeholder]
    facts: list[AccountFact]
    recent_interactions: list[InteractionSummary]
