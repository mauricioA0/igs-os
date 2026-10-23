"""Trip positions, reminder grouping/dedupe, and the guard on model-written drafts."""

from datetime import date
from uuid import UUID

from igs_common.llm import FakeLLM, Scripted
from igs_common.payments import (
    Invoice,
    ItemKind,
    Recipient,
    Stage,
    TripPlan,
    assess_trip,
    check_draft,
    draft_reminder,
    group_reminders,
)
from igs_common.payments.reminders import DETAILS, allowed_numbers, render_details
from igs_common.payments.service import risk_rows

TODAY = date(2026, 10, 22)
TRIP = UUID("00000000-0000-0000-0000-000000002711")


def lakeshore(**kw) -> TripPlan:
    base = dict(
        trip_id=TRIP,
        code="IGS-2711",
        title="Lakeshore University Women's Soccer · Buenos Aires",
        status="proposed",
        start_date=date(2027, 3, 6),
        price_per_person_usd=2890,
        travelers=24,
        account_name="Lakeshore University",
        to=Recipient("Dana Whitfield", "dwhitfield@lakeshore.example", "coach"),
        cc=(Recipient("Robert Haines", "rhaines@lakeshore.example", "athletic_director"),),
        enrollment_due=date(2026, 10, 15),
    )
    return TripPlan(**(base | kw))  # type: ignore[arg-type]


def test_lakeshore_team_enrollment_is_a_week_overdue() -> None:
    pos = assess_trip(lakeshore(), today=TODAY)
    (line,) = pos.lines
    assert (line.kind, line.seats, line.outstanding_usd, line.days) == (
        ItemKind.ENROLLMENT,
        24,
        2280,
        -7,
    )
    assert line.stage is Stage.OVERDUE_7
    assert pos.overdue_usd == 2280 and pos.oldest_overdue_days == 7
    assert not pos.cancellation_risk
    paid = assess_trip(lakeshore(paid_usd=2280), today=TODAY)
    assert paid.lines[0].stage is Stage.PAID and paid.overdue_usd == 0


def test_imported_invoices_are_the_schedule() -> None:
    invoices = (
        Invoice("INV-1042", "enrollment_fee", 2280, date(2026, 10, 15), paid_on=date(2026, 10, 14)),
        Invoice("INV-1043", "installment", 12000, date(2026, 11, 14)),
        Invoice("INV-1044", "balance", 55080, date(2026, 11, 16)),
        Invoice("INV-1045", "other", 300, date(2026, 10, 1), paid_on=date(2026, 10, 30)),
    )
    # The team-level terms are ignored once invoices exist: the operator's sheet wins.
    pos = assess_trip(lakeshore(invoices=invoices), today=TODAY)
    by_ref = {line.ref: line for line in pos.lines}
    assert by_ref["INV-1042"].stage is Stage.PAID
    assert by_ref["INV-1043"].stage is Stage.SCHEDULED and by_ref["INV-1043"].seats is None
    assert by_ref["INV-1044"].kind is ItemKind.BALANCE
    # Paid in the future (a bad cell) doesn't count as paid today.
    assert by_ref["INV-1045"].stage is Stage.OVERDUE_7 and by_ref["INV-1045"].kind is ItemKind.OTHER
    assert pos.overdue_usd == 300


def test_group_schedule_splits_the_trip_level_payment() -> None:
    # Riverside-like: 22 seats × 3180, enrolled Jun 1, 20,988 paid, departs Dec 5.
    plan = lakeshore(
        code="IGS-2715",
        status="confirmed",
        start_date=date(2026, 12, 5),
        price_per_person_usd=3180,
        travelers=22,
        enrollment_due=None,
        group_enrolled_on=date(2026, 6, 1),
        paid_usd=20988,
    )
    pos = assess_trip(plan, today=TODAY)
    assert sum(line.outstanding_usd for line in pos.lines) == 22 * 3180 - 20988
    balance = [line for line in pos.lines if line.kind is ItemKind.BALANCE]
    assert balance and all(line.due == date(2026, 8, 17) for line in balance)
    assert pos.cancellation_risk  # balance 66 days late
    # A late group enrollment (inside 110 days) owes everything at once.
    late = assess_trip(
        lakeshore(enrollment_due=None, group_enrolled_on=date(2026, 12, 1)), today=TODAY
    )
    assert [(line.kind, line.seats) for line in late.lines] == [(ItemKind.FULL, 24)]


def test_dead_or_unscheduled_trips_have_no_position() -> None:
    assert assess_trip(lakeshore(status="cancelled"), today=TODAY).lines == ()
    assert assess_trip(lakeshore(enrollment_due=None), today=TODAY).lines == ()


def _invoice_trip(*invoices: Invoice) -> TripPlan:
    return lakeshore(invoices=invoices, enrollment_due=None)


def test_reminders_group_per_trip_with_the_worst_stage_and_stable_keys() -> None:
    plan = _invoice_trip(
        Invoice("A-1", "installment", 500, date(2026, 10, 1)),  # 21 days late
        Invoice("A-2", "installment", 500, date(2026, 10, 23)),  # due tomorrow
        Invoice("A-3", "balance", 9000, date(2026, 11, 16)),  # scheduled: not in the email
    )
    (group,) = group_reminders([assess_trip(plan, today=TODAY)], today=TODAY)
    assert group.stage is Stage.OVERDUE_7  # the T-1 invoice rides along
    assert {line.ref for line in group.lines} == {"A-1", "A-2"}
    assert group.total_usd == 1000 and group.seats is None
    # Two days later A-2 is late too, but the reminder covers the same items at the same
    # escalation step: no second email. When A-1 crosses 30 days, it escalates.
    later = group_reminders([assess_trip(plan, today=date(2026, 10, 24))], today=TODAY)[0]
    assert later.dedupe_key == group.dedupe_key
    risk = group_reminders([assess_trip(plan, today=date(2026, 10, 31))], today=TODAY)[0]
    assert risk.stage is Stage.CANCELLATION_RISK and risk.dedupe_key != group.dedupe_key
    assert "invoice A-1" in render_details(group)


def _group():
    return group_reminders([assess_trip(lakeshore(), today=TODAY)], today=TODAY)[0]


def test_details_are_rendered_by_code() -> None:
    assert render_details(_group()) == (
        "- IGS-2711 · Enrollment fee · 24 travelers × US$95 · was due October 15, 2026 "
        "(7 days late) · US$2,280 outstanding\nTotal outstanding: US$2,280"
    )


def test_check_draft_only_allows_numbers_from_the_facts() -> None:
    allowed = allowed_numbers(_group())
    ok = f"Hi Dana, the enrollment for IGS-2711 is 7 days late.\n{DETAILS}\nThanks!"
    assert check_draft(ok, allowed) == []
    assert check_draft(f"Total US$2,280.\n{DETAILS}", allowed) == []
    bad = f"Please pay US$2,500 by November 12.\n{DETAILS}"
    assert check_draft(bad, allowed) == [
        "number not in the facts: 2,500",
        "number not in the facts: 12",
    ]
    assert check_draft("no placeholder", allowed) == [
        f"the draft must contain {DETAILS} exactly once"
    ]


async def test_model_draft_is_used_when_it_passes_and_sees_no_contact_data() -> None:
    llm = FakeLLM(
        [
            Scripted(
                json={
                    "subject": "IGS-2711: enrollment reminder",
                    "body": f"Hi Dana, a quick note on the enrollment.\n\n{DETAILS}\n\n— Martín",
                }
            )
        ]
    )
    draft = await draft_reminder(llm, _group())
    assert draft.source == "llm"
    assert "24 travelers × US$95" in draft.body and "US$2,280 outstanding" in draft.body
    prompt = str(llm.requests[0].items)
    assert "Dana" in prompt  # first name only
    assert "Whitfield" not in prompt and "@" not in prompt and "Haines" not in prompt


async def test_model_draft_with_an_invented_amount_falls_back_to_the_template() -> None:
    llm = FakeLLM([Scripted(json={"subject": "Reminder", "body": f"Pay US$1,999 now.\n{DETAILS}"})])
    draft = await draft_reminder(llm, _group())
    assert draft.source == "template"
    assert draft.problems == ("number not in the facts: 1,999",)
    assert "1,999" not in draft.body and "US$2,280" in draft.body


async def test_model_subject_is_checked_too() -> None:
    llm = FakeLLM([Scripted(json={"subject": "Pay by Nov 28", "body": f"Hi.\n{DETAILS}"})])
    draft = await draft_reminder(llm, _group())
    assert draft.source == "template"
    assert draft.problems == ("subject: number not in the facts: 28",)


async def test_no_model_means_template() -> None:
    draft = await draft_reminder(None, _group())
    assert draft.source == "template" and draft.subject == "IGS-2711: payments overdue"


def test_risk_rows_for_the_tool() -> None:
    plan = _invoice_trip(
        Invoice("A-1", "installment", 500, date(2026, 10, 1)),
        Invoice("A-3", "balance", 9000, date(2026, 11, 16)),
    )
    rows = risk_rows([assess_trip(plan, today=TODAY)], within_days=14)
    assert [(r["invoice_ref"], r["days"], r["late_fee_usd"]) for r in rows] == [("A-1", -21, 100)]
    wide = risk_rows([assess_trip(plan, today=TODAY)], within_days=60)
    assert [r["invoice_ref"] for r in wide] == ["A-1", "A-3"]
