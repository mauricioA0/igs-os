"""Per-traveler payment schedule and its status on a given day. Pure and deterministic.

Rules (``PaymentTerms``):

* Full plan: the whole program is due at enrollment.
* Manual plan: the enrollment fee at enrollment, each installment N days after enrollment, and
  the balance ``balance_days_before_departure`` days before departure. An installment that would
  fall on or after the balance date is folded into the balance.
* Late enrollment (on or after the balance date): everything is due at enrollment.
* Payments received are applied oldest-due first, so a traveler is never "overdue" on a later
  item while an earlier one is open.

"Today" is always the operations day in Buenos Aires (``ops_today``): a reminder run at 23:30
in Buenos Aires (02:30 UTC the next day) still belongs to that day.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timedelta
from enum import StrEnum

from igs_common.seed.anchor import OPS_TZ

from .terms import DEFAULT_TERMS, PaymentTerms


class Plan(StrEnum):
    MANUAL = "manual"  # enrollment fee + installments + balance 110 days before departure
    FULL = "full"  # everything at enrollment


class ItemKind(StrEnum):
    ENROLLMENT = "enrollment"
    INSTALLMENT_1 = "installment_1"
    INSTALLMENT_2 = "installment_2"
    INSTALLMENT_3 = "installment_3"
    INSTALLMENT = "installment"  # an imported invoice that doesn't say which one
    BALANCE = "balance"
    FULL = "full"
    OTHER = "other"


class Stage(StrEnum):
    """Where an open item stands today; also the reminder escalation step."""

    PAID = "paid"
    SCHEDULED = "scheduled"  # more than 7 days away
    T_MINUS_7 = "t_minus_7"  # due in 2..7 days
    T_MINUS_1 = "t_minus_1"  # due tomorrow or today
    OVERDUE = "overdue"  # 1..6 days late
    OVERDUE_7 = "overdue_7"  # 7..29 days late
    CANCELLATION_RISK = "cancellation_risk"  # 30+ days late

    @property
    def is_overdue(self) -> bool:
        return self in (Stage.OVERDUE, Stage.OVERDUE_7, Stage.CANCELLATION_RISK)

    @property
    def needs_reminder(self) -> bool:
        return self not in (Stage.PAID, Stage.SCHEDULED)


@dataclass(frozen=True)
class DueItem:
    kind: ItemKind
    amount_usd: int
    due: date


@dataclass(frozen=True)
class ItemStatus:
    item: DueItem
    paid_usd: int
    stage: Stage
    days: int  # due - today: negative when overdue

    @property
    def outstanding_usd(self) -> int:
        return self.item.amount_usd - self.paid_usd


def ops_today(now: datetime) -> date:
    """The operations day in Buenos Aires for an aware ``now``."""
    if now.tzinfo is None:
        raise ValueError("now must be timezone-aware")
    return now.astimezone(OPS_TZ).date()


def balance_due_date(departure: date, terms: PaymentTerms = DEFAULT_TERMS) -> date:
    return departure - timedelta(days=terms.balance_days_before_departure)


def traveler_schedule(
    *,
    price_per_person_usd: int,
    enrolled_on: date,
    departure: date,
    plan: Plan = Plan.MANUAL,
    balance_due_override: date | None = None,
    terms: PaymentTerms = DEFAULT_TERMS,
) -> tuple[DueItem, ...]:
    if price_per_person_usd <= 0:
        raise ValueError("price_per_person_usd must be positive")
    if enrolled_on > departure:
        raise ValueError("enrolled after departure")
    total = terms.program_total(price_per_person_usd)
    balance_due = balance_due_override or balance_due_date(departure, terms)
    if plan is Plan.FULL or enrolled_on >= balance_due:
        return (DueItem(ItemKind.FULL, total, enrolled_on),)

    fee = min(terms.enrollment_fee_usd, total)
    items = [DueItem(ItemKind.ENROLLMENT, fee, enrolled_on)]
    scheduled = fee
    kinds = (ItemKind.INSTALLMENT_1, ItemKind.INSTALLMENT_2, ItemKind.INSTALLMENT_3)
    for kind, (days_after, amount) in zip(kinds, terms.installments, strict=False):
        due = enrolled_on + timedelta(days=days_after)
        amount = min(amount, total - scheduled)
        if due >= balance_due or amount <= 0:
            break  # folded into the balance
        items.append(DueItem(kind, amount, due))
        scheduled += amount
    if total > scheduled:
        items.append(DueItem(ItemKind.BALANCE, total - scheduled, balance_due))
    return tuple(items)


def stage_for(days: int, terms: PaymentTerms = DEFAULT_TERMS) -> Stage:
    if days > 7:
        return Stage.SCHEDULED
    if days >= 2:
        return Stage.T_MINUS_7
    if days >= 0:
        return Stage.T_MINUS_1
    if days > -7:
        return Stage.OVERDUE
    if days > -terms.cancellation_risk_after_days:
        return Stage.OVERDUE_7
    return Stage.CANCELLATION_RISK


def apply_payments(
    items: tuple[DueItem, ...], paid_usd: int, *, today: date, terms: PaymentTerms = DEFAULT_TERMS
) -> tuple[ItemStatus, ...]:
    """Allocate ``paid_usd`` oldest-due first and classify every item for ``today``."""
    if paid_usd < 0:
        raise ValueError("paid_usd can't be negative")
    left = paid_usd
    out: list[ItemStatus] = []
    for item in sorted(items, key=lambda i: i.due):
        applied = min(left, item.amount_usd)
        left -= applied
        days = (item.due - today).days
        stage = Stage.PAID if applied >= item.amount_usd else stage_for(days, terms)
        out.append(ItemStatus(item, applied, stage, days))
    return tuple(out)
