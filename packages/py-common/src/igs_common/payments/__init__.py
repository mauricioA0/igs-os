"""Payment schedules, risks and reminders under IGS's published terms (UC-09).

Deterministic core (``terms``, ``schedule``, ``position``): amounts and dates always come from
code. The LLM only phrases reminders (``reminders``) and every draft lands in the approvals
inbox (``inbox``); nothing is sent without a person approving the exact email.
"""

from .position import Invoice, PaymentLine, Recipient, TripPlan, TripPosition, assess_trip
from .reminders import Draft, ReminderGroup, check_draft, draft_reminder, group_reminders
from .schedule import (
    DueItem,
    ItemKind,
    ItemStatus,
    Plan,
    Stage,
    apply_payments,
    balance_due_date,
    ops_today,
    traveler_schedule,
)
from .terms import DEFAULT_TERMS, PaymentTerms, refund_due

__all__ = [
    "DEFAULT_TERMS",
    "DueItem",
    "Draft",
    "Invoice",
    "ItemKind",
    "ItemStatus",
    "PaymentLine",
    "PaymentTerms",
    "Plan",
    "Recipient",
    "ReminderGroup",
    "Stage",
    "TripPlan",
    "TripPosition",
    "apply_payments",
    "assess_trip",
    "balance_due_date",
    "check_draft",
    "draft_reminder",
    "group_reminders",
    "ops_today",
    "refund_due",
    "traveler_schedule",
]
