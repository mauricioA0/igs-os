"""Inputs (exact rows from SQL) and outputs (the facts every rendering is built from).

Everything here is deterministic. The model only phrases a short summary on top of
`DigestFacts`, and that summary is checked against them (see `numbers.py`).
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from datetime import date, datetime
from decimal import Decimal
from typing import Any, Literal
from uuid import UUID

from igs_common.accounts.types import AccountSnapshot


@dataclass(frozen=True)
class DigestRules:
    departure_window_days: int = 14  # "trips departing in the next 14 days"
    payment_window_days: int = 14  # payments due within this many days (or already overdue)
    # IGS promises a reply within 1 business day of an inquiry.
    lead_sla_business_days: int = 1
    max_risks: int = 5
    max_approvals: int = 5


# ── Inputs ─────────────────────────────────────────────────────────────────


@dataclass(frozen=True)
class TripInput:
    id: UUID
    code: str | None
    title: str
    account_id: UUID | None
    account_name: str | None
    status: str  # proposed | confirmed | in_progress
    start_date: date
    end_date: date
    travelers: int | None
    total_usd: Decimal | None
    paid_usd: Decimal | None
    open_items: int  # pending or requested (not yet confirmed by the provider)

    @property
    def balance_usd(self) -> Decimal | None:
        if self.total_usd is None:
            return None
        return self.total_usd - (self.paid_usd or Decimal(0))


@dataclass(frozen=True)
class ApprovalInput:
    id: UUID
    title: str
    created_at: datetime
    expires_at: datetime | None
    subject_type: str | None
    subject_id: UUID | None


@dataclass(frozen=True)
class LeadInput:
    id: UUID
    status: str  # new | qualified
    created_at: datetime
    organization: str | None
    contact_name: str | None
    sport: str
    group_size: int
    # A person (not the web chat) wrote back: an outbound email/call/whatsapp/meeting on the lead.
    answered: bool


@dataclass(frozen=True)
class IncidentInput:
    id: UUID
    trip_id: UUID
    trip_code: str | None
    severity: str  # low | medium | high | critical
    title: str
    occurred_at: datetime


@dataclass(frozen=True)
class DigestInputs:
    accounts: tuple[AccountSnapshot, ...] = ()
    trips: tuple[TripInput, ...] = ()
    approvals: tuple[ApprovalInput, ...] = ()  # effectively pending only
    leads: tuple[LeadInput, ...] = ()  # new / qualified only
    incidents: tuple[IncidentInput, ...] = ()  # not resolved


# ── Facts ──────────────────────────────────────────────────────────────────


@dataclass(frozen=True)
class Risk:
    rank: int
    kind: Literal["account", "incident"]
    subject_id: UUID
    name: str
    level: str  # account: red | amber; incident: its severity
    reason: str
    next_action: str
    link: str


@dataclass(frozen=True)
class Payment:
    source: Literal["trip_balance", "commitment"]
    subject_id: UUID
    name: str  # account or trip
    label: str
    amount_usd: Decimal | None  # None when only a dated commitment is known
    due_date: date
    days: int  # negative = overdue by that many days
    link: str

    @property
    def overdue(self) -> bool:
        return self.days < 0


@dataclass(frozen=True)
class ApprovalItem:
    id: UUID
    title: str
    waiting_hours: int
    expires_in_hours: int | None
    link: str


@dataclass(frozen=True)
class Departure:
    trip_id: UUID
    code: str | None
    title: str
    account_name: str | None
    start_date: date
    days_to_departure: int
    open_items: int
    travelers: int | None
    link: str


@dataclass(frozen=True)
class StaleLead:
    lead_id: UUID
    organization: str
    contact_name: str | None
    sport: str
    group_size: int
    created_at: datetime
    business_days_waiting: int
    link: str


@dataclass(frozen=True)
class Counts:
    red_accounts: int
    amber_accounts: int
    risks: int
    payments_due: int
    payments_overdue: int
    approvals_pending: int
    departures: int
    stale_leads: int
    open_incidents: int


@dataclass(frozen=True)
class DigestFacts:
    day: date  # in the ops team's calendar
    generated_at: datetime
    counts: Counts
    risks: tuple[Risk, ...]
    payments: tuple[Payment, ...]
    approvals: tuple[ApprovalItem, ...]
    departures: tuple[Departure, ...]
    stale_leads: tuple[StaleLead, ...]
    rules: DigestRules = field(default_factory=DigestRules)

    def to_json(self) -> dict[str, Any]:
        data = asdict(self)
        for payment, raw in zip(self.payments, data["payments"], strict=True):
            raw["overdue"] = payment.overdue
        return json.loads(json.dumps(data, default=_json_default))


def _json_default(value: object) -> object:
    if isinstance(value, Decimal):
        return int(value) if value == value.to_integral_value() else float(value)
    if isinstance(value, date | datetime):
        return value.isoformat()
    return str(value)
