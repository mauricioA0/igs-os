from datetime import date, datetime
from datetime import time as dt_time
from typing import Any, Literal
from uuid import UUID

from igs_core.schemas.common import Schema

TripStatus = Literal["draft", "proposed", "confirmed", "in_progress", "completed", "cancelled"]
ItemStatus = Literal["pending", "requested", "confirmed", "completed", "cancelled"]
Slot = Literal["morning", "afternoon", "evening"]


class TripTeam(Schema):
    lead_id: UUID
    organization: str | None = None
    coach_name: str | None = None
    sport: str | None = None
    gender: str | None = None
    age_group: str | None = None
    level_score: int | None = None
    group_size: int | None = None


class TripSummary(Schema):
    id: UUID
    code: str | None = None
    account_id: UUID | None = None
    title: str
    city: str
    country: str
    start_date: date
    end_date: date
    status: TripStatus
    price_per_person_usd: int
    team: TripTeam


class ItemOpponent(Schema):
    name: str
    level_score: int


class ItemProvider(Schema):
    name: str
    kind: str


class TripItem(Schema):
    id: UUID
    day: int
    slot: Slot
    kind: str
    title: str
    status: ItemStatus
    opponent_id: UUID | None = None
    experience_id: UUID | None = None
    provider_id: UUID | None = None
    notes: str | None = None
    time: dt_time | None = None  # local time at the destination
    alert: str | None = None
    opponent: ItemOpponent | None = None
    provider: ItemProvider | None = None
    requested_at: datetime | None = None
    confirmed_at: datetime | None = None
    completed_at: datetime | None = None
    result: dict[str, Any] | None = None


class TripDetail(TripSummary):
    summary: str
    pricing: dict[str, Any] | None = None
    items: list[TripItem]


class TripItemPatch(Schema):
    """Partial update. Status changes follow the domain transition table."""

    status: ItemStatus | None = None
    notes: str | None = None
    requested_at: datetime | None = None
