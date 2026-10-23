"""A trip's payment position: what is owed, when, and how late. Pure and deterministic.

One source of truth for money: the trip's ledger in ``trips.pricing`` (written by the
importer, ``igs_common.importer``):

* ``pricing.payments`` — ``{payment_ref: {kind, amount_usd, due_date, paid_at}}``. When a trip
  has invoices there, **they are the schedule**: each unpaid invoice is a line, a paid one
  (``paid_at`` on or before today) is settled. The operator's own invoices always win over
  anything derived.
* ``pricing.paid_usd`` — the sum of paid invoices (or the seed's deposit while nothing has been
  imported).

When there are no invoices, the schedule is derived from IGS's terms for the group
(``pricing.payment_terms``, team-level facts no traveler row carries):

* ``enrollment_due`` — the team hasn't enrolled yet: every seat owes the enrollment fee by then
  (the Lakeshore case: 24 seats × US$95).
* ``group_enrolled_on`` — the team enrolled that day: each seat follows the manual plan
  (fee, installments, balance 110 days out) and ``paid_usd`` is spread across seats.
* ``balance_due_override`` — a negotiated balance date.

Seats are the roster size when travelers were imported, else ``trips.travelers``.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass, field
from datetime import date
from uuid import UUID

from .schedule import ItemKind, Plan, Stage, apply_payments, stage_for, traveler_schedule
from .terms import DEFAULT_TERMS, PaymentTerms

LIVE_STATUSES = frozenset({"proposed", "confirmed", "in_progress"})
_INVOICE_KINDS = {
    "enrollment_fee": ItemKind.ENROLLMENT,
    "installment": ItemKind.INSTALLMENT,
    "balance": ItemKind.BALANCE,
}


@dataclass(frozen=True)
class Invoice:
    ref: str
    kind: str  # importer PaymentKind: enrollment_fee | installment | balance | other
    amount_usd: int
    due: date
    paid_on: date | None = None


@dataclass(frozen=True)
class Recipient:
    name: str
    email: str | None
    role: str  # coach | athletic_director | decision_maker | finance | …


@dataclass(frozen=True)
class TripPlan:
    trip_id: UUID
    code: str | None
    title: str
    status: str
    start_date: date
    price_per_person_usd: int
    travelers: int | None  # seats
    account_id: UUID | None = None
    account_name: str | None = None
    to: Recipient | None = None  # the adult who receives reminders (coach / group leader)
    cc: tuple[Recipient, ...] = ()
    invoices: tuple[Invoice, ...] = ()
    paid_usd: int = 0
    enrollment_due: date | None = None
    group_enrolled_on: date | None = None
    group_plan: Plan = Plan.MANUAL
    balance_due_override: date | None = None

    @property
    def has_schedule(self) -> bool:
        return (
            bool(self.invoices)
            or self.enrollment_due is not None
            or (self.group_enrolled_on is not None)
        )


@dataclass(frozen=True)
class PaymentLine:
    trip_id: UUID
    kind: ItemKind
    due: date
    amount_usd: int  # per seat, or the invoice amount
    seats: int | None  # None for an invoice (the operator's sheet doesn't say)
    outstanding_usd: int  # for the whole line
    stage: Stage
    days: int  # due - today
    ref: str | None = None  # invoice ref, when the line is an imported invoice


@dataclass(frozen=True)
class TripPosition:
    plan: TripPlan
    lines: tuple[PaymentLine, ...] = field(default=())

    @property
    def open_lines(self) -> tuple[PaymentLine, ...]:
        return tuple(line for line in self.lines if line.stage is not Stage.PAID)

    @property
    def overdue(self) -> tuple[PaymentLine, ...]:
        return tuple(line for line in self.lines if line.stage.is_overdue)

    @property
    def overdue_usd(self) -> int:
        return sum(line.outstanding_usd for line in self.overdue)

    @property
    def oldest_overdue_days(self) -> int:
        return max((-line.days for line in self.overdue), default=0)

    @property
    def cancellation_risk(self) -> bool:
        return any(line.stage is Stage.CANCELLATION_RISK for line in self.lines)

    @property
    def next_due(self) -> PaymentLine | None:
        upcoming = [line for line in self.open_lines if not line.stage.is_overdue]
        return min(upcoming, key=lambda line: line.due, default=None)


def assess_trip(
    plan: TripPlan, *, today: date, terms: PaymentTerms = DEFAULT_TERMS
) -> TripPosition:
    if plan.status not in LIVE_STATUSES or not plan.has_schedule:
        return TripPosition(plan)
    if plan.invoices:
        lines = list(_invoice_lines(plan, today=today, terms=terms))
    elif plan.group_enrolled_on is not None and (plan.travelers or 0) > 0:
        lines = list(_group_lines(plan, plan.travelers or 0, today=today, terms=terms))
    elif plan.enrollment_due is not None and (plan.travelers or 0) > 0:
        seats = plan.travelers or 0
        fee = terms.enrollment_fee_usd
        days = (plan.enrollment_due - today).days
        settled = plan.paid_usd >= fee * seats
        lines = [
            PaymentLine(
                plan.trip_id,
                ItemKind.ENROLLMENT,
                plan.enrollment_due,
                fee,
                seats,
                0 if settled else fee * seats - plan.paid_usd,
                Stage.PAID if settled else stage_for(days, terms),
                days,
            )
        ]
    else:
        lines = []
    return TripPosition(plan, tuple(sorted(lines, key=lambda line: (line.due, line.kind.value))))


def _invoice_lines(plan: TripPlan, *, today: date, terms: PaymentTerms) -> Iterable[PaymentLine]:
    for inv in plan.invoices:
        paid = inv.paid_on is not None and inv.paid_on <= today
        days = (inv.due - today).days
        yield PaymentLine(
            plan.trip_id,
            _INVOICE_KINDS.get(inv.kind, ItemKind.OTHER),
            inv.due,
            inv.amount_usd,
            None,
            0 if paid else inv.amount_usd,
            Stage.PAID if paid else stage_for(days, terms),
            days,
            inv.ref,
        )


def _group_lines(
    plan: TripPlan, seats: int, *, today: date, terms: PaymentTerms
) -> Iterable[PaymentLine]:
    """``seats`` identical travelers; ``paid_usd`` is split evenly (remainder to the first
    seats), so the result reads like a per-traveler ledger would."""
    assert plan.group_enrolled_on is not None
    items = traveler_schedule(
        price_per_person_usd=plan.price_per_person_usd,
        enrolled_on=min(plan.group_enrolled_on, plan.start_date),
        departure=plan.start_date,
        plan=plan.group_plan,
        balance_due_override=plan.balance_due_override,
        terms=terms,
    )
    share, extra = divmod(plan.paid_usd, seats)
    buckets: dict[tuple[ItemKind, date, Stage], list[int]] = {}
    for n in range(seats):
        paid = share + (1 if n < extra else 0)
        for s in apply_payments(items, paid, today=today, terms=terms):
            buckets.setdefault((s.item.kind, s.item.due, s.stage), []).append(s.outstanding_usd)
    by_item = {(i.kind, i.due): i for i in items}
    for (kind, due, stage), owed in buckets.items():
        yield PaymentLine(
            plan.trip_id,
            kind,
            due,
            by_item[(kind, due)].amount_usd,
            len(owed),
            sum(owed),
            stage,
            (due - today).days,
        )
