from datetime import date, datetime
from typing import Literal
from uuid import UUID

from pydantic import Field

from igs_core.schemas.common import Schema

LeadStatus = Literal["new", "qualified", "proposal_sent", "won", "lost"]


class LeadContact(Schema):
    id: UUID
    name: str
    email: str | None = None
    organization: str | None = None
    role: str | None = None


class LeadSummary(Schema):
    id: UUID
    status: LeadStatus
    source: str
    account_id: UUID | None = None
    account_name: str | None = None
    contact: LeadContact | None = None
    sport: str
    gender: str
    age_group: str
    level_score: int
    group_size: int
    destination_country: str
    travel_start: date
    duration_days: int
    budget_per_person_usd: int | None = None
    lost_reason: str | None = None
    # The latest trip drafted for this lead, if any.
    trip_id: UUID | None = None
    trip_code: str | None = None
    created_at: datetime
    updated_at: datetime


class LeadDetail(LeadSummary):
    goals: str | None = None
    conversation_id: UUID | None = None


class LeadPatch(Schema):
    """Status changes follow the domain transitions; `lost` requires a reason."""

    status: LeadStatus | None = None
    lost_reason: str | None = Field(default=None, max_length=500)
    goals: str | None = Field(default=None, max_length=4000)
