"""Allowed status transitions for leads, trips, trip items and approvals."""

from __future__ import annotations

from collections.abc import Mapping
from enum import StrEnum

from .enums import ApprovalStatus, ItemStatus, LeadStatus, TripStatus


class InvalidTransition(ValueError):
    def __init__(self, entity: str, current: StrEnum, target: StrEnum) -> None:
        super().__init__(f"{entity}: {current.value} → {target.value} is not allowed")
        self.entity, self.current, self.target = entity, current, target


L, T, I, A = LeadStatus, TripStatus, ItemStatus, ApprovalStatus  # noqa: E741

LEAD_TRANSITIONS: Mapping[LeadStatus, frozenset[LeadStatus]] = {
    L.NEW: frozenset({L.QUALIFIED, L.LOST}),
    L.QUALIFIED: frozenset({L.PROPOSAL_SENT, L.LOST}),
    # A revised proposal sends the lead back to qualified.
    L.PROPOSAL_SENT: frozenset({L.WON, L.LOST, L.QUALIFIED}),
    L.WON: frozenset(),
    L.LOST: frozenset({L.QUALIFIED}),  # reopened
}

TRIP_TRANSITIONS: Mapping[TripStatus, frozenset[TripStatus]] = {
    T.DRAFT: frozenset({T.PROPOSED, T.CANCELLED}),
    T.PROPOSED: frozenset({T.CONFIRMED, T.DRAFT, T.CANCELLED}),
    T.CONFIRMED: frozenset({T.IN_PROGRESS, T.CANCELLED}),
    T.IN_PROGRESS: frozenset({T.COMPLETED}),
    T.COMPLETED: frozenset(),
    T.CANCELLED: frozenset(),
}

ITEM_TRANSITIONS: Mapping[ItemStatus, frozenset[ItemStatus]] = {
    I.PENDING: frozenset({I.REQUESTED, I.CONFIRMED, I.CANCELLED}),
    I.REQUESTED: frozenset({I.CONFIRMED, I.CANCELLED, I.PENDING}),
    # A change to a confirmed item (time, opponent) needs reconfirmation.
    I.CONFIRMED: frozenset({I.PENDING, I.COMPLETED, I.CANCELLED}),
    I.COMPLETED: frozenset(),  # it happened; a correction is a new item, not a reopen
    I.CANCELLED: frozenset({I.PENDING}),
}

APPROVAL_TRANSITIONS: Mapping[ApprovalStatus, frozenset[ApprovalStatus]] = {
    A.PENDING: frozenset({A.APPROVED, A.REJECTED, A.EXPIRED}),
    A.APPROVED: frozenset(),
    A.REJECTED: frozenset(),
    A.EXPIRED: frozenset(),
}

# Transitions that are external/destructive and must go through an approval.
DESTRUCTIVE: frozenset[tuple[str, StrEnum]] = frozenset({("trip", T.CANCELLED)})

_TABLES: dict[str, Mapping] = {
    "lead": LEAD_TRANSITIONS,
    "trip": TRIP_TRANSITIONS,
    "trip_item": ITEM_TRANSITIONS,
    "approval": APPROVAL_TRANSITIONS,
}


def can_transition(entity: str, current: StrEnum, target: StrEnum) -> bool:
    return target in _TABLES[entity][current]


def assert_transition(entity: str, current: StrEnum, target: StrEnum) -> None:
    if not can_transition(entity, current, target):
        raise InvalidTransition(entity, current, target)


def is_terminal(entity: str, status: StrEnum) -> bool:
    return not _TABLES[entity][status]


def needs_approval(entity: str, target: StrEnum) -> bool:
    return (entity, target) in DESTRUCTIVE
