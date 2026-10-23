"""Schedule rules from IGS's terms: US$95 at enrollment, US$500 at +30 and +90 days, balance
110 days before departure, oldest-due-first allocation, Buenos Aires operations day."""

from datetime import UTC, date, datetime, timedelta

import pytest

from igs_common.payments import (
    ItemKind,
    PaymentTerms,
    Plan,
    Stage,
    apply_payments,
    balance_due_date,
    ops_today,
    refund_due,
    traveler_schedule,
)

DEPARTURE = date(2027, 3, 6)  # Lakeshore IGS-2711


def kinds(items):
    return [(i.kind, i.amount_usd, i.due) for i in items]


def test_manual_plan_follows_the_published_terms() -> None:
    items = traveler_schedule(
        price_per_person_usd=2890, enrolled_on=date(2026, 7, 1), departure=DEPARTURE
    )
    assert balance_due_date(DEPARTURE) == date(2026, 11, 16)  # the date the proposal quotes
    assert kinds(items) == [
        (ItemKind.ENROLLMENT, 95, date(2026, 7, 1)),
        (ItemKind.INSTALLMENT_1, 500, date(2026, 7, 31)),
        (ItemKind.INSTALLMENT_2, 500, date(2026, 9, 29)),
        (ItemKind.BALANCE, 2890 - 1095, date(2026, 11, 16)),
    ]
    assert sum(i.amount_usd for i in items) == 2890


def test_installments_past_the_balance_date_fold_into_the_balance() -> None:
    # Enrolls Oct 1: +30 = Oct 31 fits, +90 = Dec 30 is after Nov 16 → folded.
    items = traveler_schedule(
        price_per_person_usd=2890, enrolled_on=date(2026, 10, 1), departure=DEPARTURE
    )
    assert [i.kind for i in items] == [
        ItemKind.ENROLLMENT,
        ItemKind.INSTALLMENT_1,
        ItemKind.BALANCE,
    ]
    assert items[-1].amount_usd == 2890 - 595


@pytest.mark.parametrize("enrolled", [date(2026, 11, 16), date(2026, 12, 20), DEPARTURE])
def test_late_enrollment_inside_110_days_pays_everything_at_enrollment(enrolled: date) -> None:
    items = traveler_schedule(price_per_person_usd=2890, enrolled_on=enrolled, departure=DEPARTURE)
    assert kinds(items) == [(ItemKind.FULL, 2890, enrolled)]


def test_one_day_before_the_balance_date_keeps_the_fee_separate() -> None:
    items = traveler_schedule(
        price_per_person_usd=2890, enrolled_on=date(2026, 11, 15), departure=DEPARTURE
    )
    assert kinds(items) == [
        (ItemKind.ENROLLMENT, 95, date(2026, 11, 15)),
        (ItemKind.BALANCE, 2795, date(2026, 11, 16)),
    ]


def test_full_plan_and_cheap_programs() -> None:
    full = traveler_schedule(
        price_per_person_usd=2890, enrolled_on=date(2026, 7, 1), departure=DEPARTURE, plan=Plan.FULL
    )
    assert kinds(full) == [(ItemKind.FULL, 2890, date(2026, 7, 1))]
    # A US$800 camp: the second installment would exceed the price; nothing is negative.
    cheap = traveler_schedule(
        price_per_person_usd=800, enrolled_on=date(2026, 7, 1), departure=DEPARTURE
    )
    assert kinds(cheap) == [
        (ItemKind.ENROLLMENT, 95, date(2026, 7, 1)),
        (ItemKind.INSTALLMENT_1, 500, date(2026, 7, 31)),
        (ItemKind.INSTALLMENT_2, 205, date(2026, 9, 29)),
    ]


def test_negotiated_balance_date_and_fee_on_top() -> None:
    items = traveler_schedule(
        price_per_person_usd=2890,
        enrolled_on=date(2026, 7, 1),
        departure=DEPARTURE,
        balance_due_override=date(2026, 12, 1),
        terms=PaymentTerms(fee_included_in_price=False),
    )
    assert sum(i.amount_usd for i in items) == 2890 + 95
    assert (items[-1].kind, items[-1].amount_usd, items[-1].due) == (
        ItemKind.BALANCE,
        2890 + 95 - 1095,
        date(2026, 12, 1),
    )


def test_bad_inputs() -> None:
    with pytest.raises(ValueError):
        traveler_schedule(price_per_person_usd=0, enrolled_on=DEPARTURE, departure=DEPARTURE)
    with pytest.raises(ValueError):
        traveler_schedule(
            price_per_person_usd=10, enrolled_on=DEPARTURE + timedelta(1), departure=DEPARTURE
        )
    with pytest.raises(ValueError):
        apply_payments((), -1, today=DEPARTURE)


def test_payments_apply_oldest_first_and_stages_escalate() -> None:
    items = traveler_schedule(
        price_per_person_usd=2890, enrolled_on=date(2026, 7, 1), departure=DEPARTURE
    )
    # Paid the fee and half of the first installment.
    status = apply_payments(items, 345, today=date(2026, 8, 7))
    by_kind = {s.item.kind: s for s in status}
    assert by_kind[ItemKind.INSTALLMENT_1].outstanding_usd == 250
    assert by_kind[ItemKind.INSTALLMENT_1].days == -7
    assert by_kind[ItemKind.INSTALLMENT_1].stage is Stage.OVERDUE_7


@pytest.mark.parametrize(
    ("days", "stage"),
    [
        (8, Stage.SCHEDULED),
        (7, Stage.T_MINUS_7),
        (2, Stage.T_MINUS_7),
        (1, Stage.T_MINUS_1),
        (0, Stage.T_MINUS_1),
        (-1, Stage.OVERDUE),
        (-6, Stage.OVERDUE),
        (-7, Stage.OVERDUE_7),
        (-29, Stage.OVERDUE_7),
        (-30, Stage.CANCELLATION_RISK),
    ],
)
def test_stage_boundaries(days: int, stage: Stage) -> None:
    due = date(2026, 10, 22)
    items = traveler_schedule(price_per_person_usd=95, enrolled_on=due, departure=DEPARTURE)
    (s,) = apply_payments(items, 0, today=due - timedelta(days=days))
    assert s.stage is stage


def test_operations_day_is_buenos_aires() -> None:
    # 02:30 UTC on Oct 23 is 23:30 on Oct 22 in Buenos Aires (UTC-3, no DST).
    assert ops_today(datetime(2026, 10, 23, 2, 30, tzinfo=UTC)) == date(2026, 10, 22)
    assert ops_today(datetime(2026, 10, 23, 3, 0, tzinfo=UTC)) == date(2026, 10, 23)
    with pytest.raises(ValueError):
        ops_today(datetime(2026, 10, 23, 2, 30))


def test_due_tonight_in_buenos_aires_is_not_overdue_yet() -> None:
    due = date(2026, 10, 22)
    items = traveler_schedule(price_per_person_usd=95, enrolled_on=due, departure=DEPARTURE)
    late_evening = ops_today(datetime(2026, 10, 23, 2, 30, tzinfo=UTC))
    (s,) = apply_payments(items, 0, today=late_evening)
    assert s.stage is Stage.T_MINUS_1 and s.days == 0


@pytest.mark.parametrize(
    ("days_before", "refund"),
    [
        (200, 2890 - 95),
        (150, 2890 - 95),
        (149, 2890 - 95 - 300),
        (110, 2890 - 95 - 300),
        (109, 2890 - 95 - 1445),
        (45, 2890 - 95 - 1445),
        (44, 0),
        (-3, 0),
    ],
)
def test_tiered_refunds(days_before: int, refund: int) -> None:
    assert (
        refund_due(price_per_person_usd=2890, paid_usd=2890, days_before_departure=days_before)
        == refund
    )


def test_refund_never_negative() -> None:
    assert refund_due(price_per_person_usd=2890, paid_usd=95, days_before_departure=120) == 0
