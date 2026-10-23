"""In-memory digest inputs around the Lakeshore story (see tests/accounts/helpers.py)."""

from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from uuid import UUID

from igs_common.accounts.types import FactView
from igs_common.db.enums import FactKind
from igs_common.digest import ApprovalInput, DigestInputs, IncidentInput, LeadInput, TripInput

from ..accounts.helpers import ACCOUNT, EMAIL, snapshot

# Thursday 22 Oct 2026, 12:00 UTC = 09:00 in Buenos Aires.
NOW = datetime(2026, 10, 22, 12, tzinfo=UTC)
TODAY = date(2026, 10, 22)

FEES_RISK = FactView(
    id=UUID(int=201),
    kind=FactKind.RISK,
    statement="The team's enrollment fees (24 × US$95 = US$2,280) are overdue.",
    confidence=0.95,
    source_interaction_id=EMAIL.id,
    valid_from=EMAIL.occurred_at,
    severity="high",
    due_date=date(2026, 10, 31),
)
DECISION = FactView(
    id=UUID(int=202),
    kind=FactKind.COMMITMENT,
    statement="Haines decides by October 31 after the budget meeting.",
    confidence=0.9,
    source_interaction_id=EMAIL.id,
    valid_from=EMAIL.occurred_at,
    due_date=date(2026, 10, 31),
)

LAKESHORE = snapshot(facts=(FEES_RISK, DECISION))
QUIET = snapshot(account_id=UUID(int=3), name="Quiet College", facts=())

TRIP_ID = UUID(int=300)
APPROVAL = ApprovalInput(
    id=UUID(int=9003),
    title="Enviar la propuesta IGS-2711 a Dana Whitfield",
    created_at=NOW - timedelta(hours=20),
    expires_at=NOW + timedelta(hours=30),
    subject_type="trip",
    subject_id=TRIP_ID,
)


def trip_input(**overrides: object) -> TripInput:
    data: dict[str, object] = {
        "id": TRIP_ID,
        "code": "IGS-2711",
        "title": "Lakeshore University Women's Soccer · Buenos Aires",
        "account_id": ACCOUNT,
        "account_name": "Lakeshore University",
        "status": "proposed",
        "start_date": date(2027, 3, 7),
        "end_date": date(2027, 3, 16),
        "travelers": 24,
        "total_usd": Decimal(69360),
        "paid_usd": Decimal(0),
        "open_items": 3,
    }
    data.update(overrides)
    return TripInput(**data)  # type: ignore[arg-type]


def lead(**overrides: object) -> LeadInput:
    data: dict[str, object] = {
        "id": UUID(int=500),
        "status": "new",
        "created_at": NOW - timedelta(days=3),  # Monday
        "organization": "Harbor Point Academy",
        "contact_name": "Lee Carter",
        "sport": "basketball",
        "group_size": 16,
        "answered": False,
    }
    data.update(overrides)
    return LeadInput(**data)  # type: ignore[arg-type]


def inputs(**overrides: object) -> DigestInputs:
    data: dict[str, object] = {
        "accounts": (LAKESHORE, QUIET),
        "trips": (trip_input(),),
        "approvals": (APPROVAL,),
        "leads": (lead(),),
        "incidents": (),
    }
    data.update(overrides)
    return DigestInputs(**data)  # type: ignore[arg-type]


INCIDENT = IncidentInput(
    id=UUID(int=700),
    trip_id=UUID(int=301),
    trip_code="IGS-2715",
    severity="critical",
    title="Bus did not show up at the hotel",
    occurred_at=NOW - timedelta(hours=1),
)
