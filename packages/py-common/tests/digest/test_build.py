from dataclasses import replace
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal

from igs_common.digest import add_business_days, build_digest, business_days_between

from .helpers import APPROVAL, INCIDENT, NOW, TODAY, inputs, lead, trip_input


def test_red_client_ranks_first_with_reason_and_next_action_from_records() -> None:
    facts = build_digest(inputs(), now=NOW)
    top = facts.risks[0]
    assert (top.rank, top.name, top.level) == (1, "Lakeshore University", "red")
    assert top.reason.startswith("Riesgo abierto: The team's enrollment fees")
    # A pending approval about one of the client's trips is the first thing to do.
    assert top.next_action == f"Decidir la aprobación «{APPROVAL.title}»"
    assert top.link == f"/ops/accounts/{top.subject_id}"
    assert facts.counts.red_accounts == 1 and facts.counts.amber_accounts == 0
    assert [r.name for r in facts.risks] == ["Lakeshore University"]  # green clients stay out


def test_without_an_approval_the_soonest_dated_commitment_is_the_next_action() -> None:
    facts = build_digest(inputs(approvals=()), now=NOW)
    assert facts.risks[0].next_action.startswith("Antes del 31/10: ")


def test_critical_incident_outranks_a_red_client() -> None:
    facts = build_digest(inputs(incidents=(INCIDENT,)), now=NOW)
    assert [r.kind for r in facts.risks] == ["incident", "account"]
    assert facts.risks[0].link == f"/ops/trips/{INCIDENT.trip_id}"
    low = replace(INCIDENT, severity="low")
    assert [r.kind for r in build_digest(inputs(incidents=(low,)), now=NOW).risks] == ["account"]


def test_payments_include_dated_money_commitments_and_balances_due_soon() -> None:
    # Departure 120 days out → final balance due in 10 days (IGS terms: 110 days before).
    soon = trip_input(start_date=TODAY + timedelta(days=120), paid_usd=Decimal(20000))
    facts = build_digest(inputs(trips=(soon,)), now=NOW)
    by_source = {p.source: p for p in facts.payments}
    balance = by_source["trip_balance"]
    assert (balance.amount_usd, balance.days, balance.overdue) == (Decimal(49360), 10, False)
    fees = by_source["commitment"]
    assert fees.label.startswith("The team's enrollment fees") and fees.amount_usd is None
    assert fees.due_date == date(2026, 10, 31)
    # The decision commitment has a date but is not about money.
    assert len(facts.payments) == 2


def test_overdue_balance_is_flagged_and_sorted_first() -> None:
    late = trip_input(start_date=TODAY + timedelta(days=100))
    facts = build_digest(inputs(trips=(late,)), now=NOW)
    assert facts.payments[0].overdue and facts.payments[0].days == -10
    assert facts.counts.payments_overdue == 1


def test_paid_or_far_balances_are_not_listed() -> None:
    paid = trip_input(start_date=TODAY + timedelta(days=100), paid_usd=Decimal(69360))
    far = trip_input(start_date=TODAY + timedelta(days=200))
    for trip in (paid, far):
        facts = build_digest(inputs(trips=(trip,)), now=NOW)
        assert [p.source for p in facts.payments] == ["commitment"]


def test_departures_within_14_days_only_and_with_open_items() -> None:
    leaving = trip_input(status="confirmed", start_date=TODAY + timedelta(days=14), open_items=2)
    later = trip_input(status="confirmed", start_date=TODAY + timedelta(days=15))
    live = trip_input(status="in_progress", start_date=TODAY - timedelta(days=2))
    facts = build_digest(inputs(trips=(leaving, later, live)), now=NOW)
    assert [(d.days_to_departure, d.open_items) for d in facts.departures] == [(14, 2)]


def test_approvals_oldest_first_with_hours() -> None:
    newer = replace(APPROVAL, id=APPROVAL.id.__class__(int=9004), created_at=NOW, expires_at=None)
    facts = build_digest(inputs(approvals=(newer, APPROVAL)), now=NOW)
    assert [a.waiting_hours for a in facts.approvals] == [20, 0]
    assert facts.approvals[0].expires_in_hours == 30 and facts.approvals[1].expires_in_hours is None
    assert facts.approvals[0].link == f"/ops/approvals?id={APPROVAL.id}"


def test_lead_unanswered_past_one_business_day_is_stale() -> None:
    facts = build_digest(inputs(), now=NOW)
    [stale] = facts.stale_leads
    assert stale.organization == "Harbor Point Academy" and stale.business_days_waiting == 3


def test_answered_or_recent_leads_are_not_stale() -> None:
    answered = lead(answered=True)
    recent = lead(created_at=NOW - timedelta(hours=20))
    assert build_digest(inputs(leads=(answered, recent)), now=NOW).stale_leads == ()


def test_friday_inquiry_is_due_monday_and_weekend_inquiry_tuesday() -> None:
    friday = datetime(2026, 10, 23, 18, tzinfo=UTC)  # 15:00 Buenos Aires
    assert add_business_days(friday, 1) == datetime(2026, 10, 26, 18, tzinfo=UTC)
    saturday = datetime(2026, 10, 24, 15, tzinfo=UTC)
    assert add_business_days(saturday, 1) == datetime(2026, 10, 27, 12, tzinfo=UTC)
    monday_noon = datetime(2026, 10, 26, 15, tzinfo=UTC)
    stale = build_digest(inputs(leads=(lead(created_at=friday),)), now=monday_noon)
    assert stale.stale_leads == ()  # Monday 12:00 < Monday 15:00 deadline
    assert business_days_between(friday, datetime(2026, 10, 27, 12, tzinfo=UTC)) == 2


def test_today_is_the_buenos_aires_day() -> None:
    late_night = datetime(2026, 10, 23, 2, tzinfo=UTC)  # still the 22nd in Buenos Aires
    assert build_digest(inputs(), now=late_night).day == date(2026, 10, 22)


def test_json_is_serializable_and_flags_overdue() -> None:
    late = trip_input(start_date=TODAY + timedelta(days=100))
    data = build_digest(inputs(trips=(late,)), now=NOW).to_json()
    assert data["payments"][0]["overdue"] is True
    assert data["payments"][0]["amount_usd"] == 69360
    assert data["day"] == "2026-10-22"
