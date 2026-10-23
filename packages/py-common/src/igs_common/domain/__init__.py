"""Pure domain logic: no I/O, no framework. Safe to call from API, workers and tests."""

from .approvals import canonical_json, payload_hash, verify_payload
from .planner import (
    ExperienceCandidate,
    Itinerary,
    OpponentCandidate,
    PlannedItem,
    ProviderCandidate,
    TeamProfile,
    plan_itinerary,
)
from .pricing import Quote, QuoteLine, quote
from .tools import Decision, Principal, ToolClass, ToolSpec, TriggerTrust, decide, trigger_trust
from .transitions import InvalidTransition, assert_transition, can_transition

__all__ = [
    "Decision",
    "ExperienceCandidate",
    "InvalidTransition",
    "Itinerary",
    "OpponentCandidate",
    "PlannedItem",
    "Principal",
    "ProviderCandidate",
    "Quote",
    "QuoteLine",
    "TeamProfile",
    "ToolClass",
    "ToolSpec",
    "TriggerTrust",
    "assert_transition",
    "can_transition",
    "canonical_json",
    "decide",
    "payload_hash",
    "plan_itinerary",
    "quote",
    "trigger_trust",
    "verify_payload",
]
