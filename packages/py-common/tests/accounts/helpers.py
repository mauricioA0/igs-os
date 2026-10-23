"""Builders for in-memory Account 360 snapshots."""

from datetime import UTC, date, datetime
from decimal import Decimal
from uuid import UUID

from igs_common.accounts.types import (
    AccountSnapshot,
    FactView,
    InteractionView,
    StakeholderView,
    TripView,
)
from igs_common.db.enums import (
    AccountHealth,
    AccountKind,
    AccountStatus,
    Direction,
    FactKind,
    InteractionChannel,
    Sentiment,
    StakeholderRole,
    TripStatus,
)

TENANT = UUID(int=1)
ACCOUNT = UUID(int=2)
TODAY = date(2026, 10, 22)
NOW = datetime(2026, 10, 22, 12, tzinfo=UTC)

HAINES = StakeholderView(
    id=UUID(int=10),
    name="Robert Haines",
    title="Sr. Associate AD",
    role=StakeholderRole.DECISION_MAKER,
    influence=5,
    sentiment=Sentiment.NEUTRAL,
    last_contact_at=datetime(2026, 10, 20, tzinfo=UTC),
)
WHITFIELD = StakeholderView(
    id=UUID(int=11),
    name="Dana Whitfield",
    title="Head Coach",
    role=StakeholderRole.COACH,
    influence=4,
    sentiment=Sentiment.POSITIVE,
    last_contact_at=datetime(2026, 10, 21, tzinfo=UTC),
)

EMAIL = InteractionView(
    id=UUID(int=100),
    occurred_at=datetime(2026, 10, 20, 15, tzinfo=UTC),
    channel=InteractionChannel.EMAIL,
    direction=Direction.INBOUND,
    subject="PO approved",
    stakeholder_name="Robert Haines",
    body=(
        "Hi Martín — the purchase order was approved today. AP will release the "
        "USD 48,552 balance within five business days."
    ),
)
CALL = InteractionView(
    id=UUID(int=101),
    occurred_at=datetime(2026, 10, 21, 18, tzinfo=UTC),
    channel=InteractionChannel.CALL,
    direction=Direction.OUTBOUND,
    subject=None,
    stakeholder_name="Dana Whitfield",
    body="Coach confirmed two players are gluten-free and one is vegetarian.",
)

BALANCE_FACT = FactView(
    id=UUID(int=200),
    kind=FactKind.COMMITMENT,
    statement="AP will pay the USD 48,552 balance within five business days of Oct 20.",
    confidence=0.9,
    source_interaction_id=EMAIL.id,
    valid_from=EMAIL.occurred_at,
)


def trip(**overrides: object) -> TripView:
    data: dict[str, object] = {
        "id": UUID(int=300),
        "code": "IGS-2711",
        "title": "Lakeshore University Women's Soccer · Buenos Aires",
        "status": TripStatus.CONFIRMED,
        "start_date": date(2027, 3, 7),
        "end_date": date(2027, 3, 16),
        "total_usd": Decimal(69360),
        "paid_usd": Decimal(69360),
    }
    data.update(overrides)
    return TripView(**data)  # type: ignore[arg-type]


def snapshot(**overrides: object) -> AccountSnapshot:
    data: dict[str, object] = {
        "tenant_id": TENANT,
        "account_id": ACCOUNT,
        "name": "Lakeshore University",
        "kind": AccountKind.UNIVERSITY,
        "status": AccountStatus.ACTIVE,
        "stored_health": AccountHealth.GREEN,
        "location": "Port Huron, Michigan, USA",
        "sport_programs": ("womens_soccer",),
        "stakeholders": (HAINES, WHITFIELD),
        "facts": (),
        "interactions": (CALL, EMAIL),
        "trips": (trip(),),
    }
    data.update(overrides)
    return AccountSnapshot(**data)  # type: ignore[arg-type]
