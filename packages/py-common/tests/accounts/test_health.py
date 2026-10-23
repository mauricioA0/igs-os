from dataclasses import replace
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from uuid import UUID

from igs_common.accounts import compute_health
from igs_common.db.enums import AccountHealth, FactKind, Sentiment

from .helpers import BALANCE_FACT, HAINES, TODAY, WHITFIELD, snapshot, trip


def test_green_when_nothing_is_open() -> None:
    result = compute_health(snapshot(), today=TODAY)
    assert result.health is AccountHealth.GREEN


def test_open_risk_is_amber_and_high_severity_is_red() -> None:
    risk = replace(BALANCE_FACT, kind=FactKind.RISK, statement="Rooming list unconfirmed.")
    assert compute_health(snapshot(facts=(risk,)), today=TODAY).health is AccountHealth.AMBER
    high = replace(risk, severity="high")
    result = compute_health(snapshot(facts=(high,)), today=TODAY)
    assert result.health is AccountHealth.RED
    assert any("Rooming list" in r for r in result.reasons)


def test_closed_or_non_risk_facts_do_not_count() -> None:
    done = replace(BALANCE_FACT, kind=FactKind.RISK, severity="high", status="done")
    assert compute_health(snapshot(facts=(done, BALANCE_FACT)), today=TODAY).health is (
        AccountHealth.GREEN
    )


def test_negative_decision_maker_is_red() -> None:
    upset = replace(HAINES, sentiment=Sentiment.NEGATIVE)
    result = compute_health(snapshot(stakeholders=(upset, WHITFIELD)), today=TODAY)
    assert result.health is AccountHealth.RED


def test_balance_overdue_close_to_departure_is_red() -> None:
    soon = trip(start_date=date(2026, 11, 14), end_date=date(2026, 11, 23), paid_usd=Decimal(20808))
    result = compute_health(snapshot(trips=(soon,)), today=TODAY)
    assert result.health is AccountHealth.RED
    assert any("Saldo vencido" in r and "23 días" in r for r in result.reasons)


def test_balance_overdue_far_from_departure_is_amber() -> None:
    later = trip(start_date=date(2026, 12, 1), end_date=date(2026, 12, 10), paid_usd=Decimal(0))
    assert compute_health(snapshot(trips=(later,)), today=TODAY).health is AccountHealth.AMBER


def test_balance_due_soon_is_amber() -> None:
    # due = start - 110 days (IGS terms) = Nov 1 → 10 days away
    upcoming = trip(start_date=date(2027, 2, 19), end_date=date(2027, 2, 28), paid_usd=None)
    result = compute_health(snapshot(trips=(upcoming,)), today=TODAY)
    assert result.health is AccountHealth.AMBER
    assert any("vence" in r for r in result.reasons)


def test_cancelled_trips_are_ignored() -> None:
    from igs_common.db.enums import TripStatus

    gone = trip(status=TripStatus.CANCELLED, start_date=date(2026, 11, 1), paid_usd=Decimal(0))
    assert compute_health(snapshot(trips=(gone,)), today=TODAY).health is AccountHealth.GREEN


def test_stale_decision_maker_contact_is_amber() -> None:
    stale = replace(HAINES, last_contact_at=datetime(2026, 9, 1, tzinfo=UTC))
    result = compute_health(snapshot(stakeholders=(stale, WHITFIELD)), today=TODAY)
    assert result.health is AccountHealth.AMBER
    assert any("Robert Haines" in r for r in result.reasons)


def _position(start: date, *, enrollment_due: date | None = None, enrolled_on=None, paid=0):
    from igs_common.payments import TripPlan, assess_trip

    plan = TripPlan(
        trip_id=UUID(int=300),
        code="IGS-2711",
        title="Lakeshore",
        status="confirmed",
        start_date=start,
        price_per_person_usd=2890,
        travelers=24,
        enrollment_due=enrollment_due,
        group_enrolled_on=enrolled_on,
        paid_usd=paid,
    )
    return assess_trip(plan, today=TODAY)


def test_payment_schedule_replaces_the_trip_total_rule() -> None:
    # Team enrollment a week late: amber with the exact amount, no legacy "Saldo" reason.
    late = _position(date(2027, 3, 7), enrollment_due=TODAY - timedelta(days=7))
    t = trip(payments=late, paid_usd=Decimal(0))
    result = compute_health(snapshot(trips=(t,)), today=TODAY)
    assert result.health is AccountHealth.AMBER
    assert result.reasons[0].startswith("Pagos vencidos de US$ 2.280 en IGS-2711 (24 plazas")
    assert not any(r.startswith("Saldo") for r in result.reasons)


def test_payment_schedule_cancellation_risk_and_upcoming() -> None:
    risk = _position(date(2027, 3, 7), enrollment_due=TODAY - timedelta(days=30))
    result = compute_health(snapshot(trips=(trip(payments=risk),)), today=TODAY)
    assert result.health is AccountHealth.RED
    assert "riesgo de cancelación" in result.reasons[0]

    soon = _position(date(2027, 3, 7), enrollment_due=TODAY + timedelta(days=10))
    result = compute_health(snapshot(trips=(trip(payments=soon),)), today=TODAY)
    assert result.health is AccountHealth.AMBER
    assert result.reasons[0].startswith("US$ 2.280 vence el")
