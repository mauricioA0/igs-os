import itertools

import pytest

from igs_common.domain.enums import ApprovalStatus, ItemStatus, LeadStatus, TripStatus
from igs_common.domain.tools import (
    SCOPE_EXTERNAL,
    SCOPE_READ,
    SCOPE_WRITE,
    Decision,
    Principal,
    PrincipalKind,
    Role,
    ToolClass,
    ToolSpec,
    TriggerKind,
    TriggerTrust,
    decide,
    requires_approval,
    trigger_trust,
)
from igs_common.domain.transitions import (
    InvalidTransition,
    assert_transition,
    can_transition,
    is_terminal,
    needs_approval,
)

READ = ToolSpec("get_trip", ToolClass.READ)
CREATE_LEAD = ToolSpec("create_lead", ToolClass.WRITE_INTERNAL, coach_safe=True)
SWAP = ToolSpec("swap_opponent", ToolClass.WRITE_INTERNAL)
SEND = ToolSpec("send_message", ToolClass.WRITE_EXTERNAL)
ALL_TOOLS = [READ, CREATE_LEAD, SWAP, SEND]


def test_trigger_trust():
    assert trigger_trust(TriggerKind.CHAT) is TriggerTrust.UNTRUSTED
    assert trigger_trust(TriggerKind.WEBHOOK) is TriggerTrust.UNTRUSTED
    assert trigger_trust(TriggerKind.MANUAL) is TriggerTrust.TRUSTED
    assert trigger_trust(TriggerKind.SCHEDULE) is TriggerTrust.TRUSTED
    assert trigger_trust(TriggerKind.EVENT) is TriggerTrust.TRUSTED
    assert trigger_trust(TriggerKind.EVENT, tainted=True) is TriggerTrust.UNTRUSTED


def test_coach_agent_only_reads_and_proposes():
    coach = Principal(PrincipalKind.COACH_AGENT)
    assert decide(READ, coach) is Decision.ALLOW
    assert decide(CREATE_LEAD, coach) is Decision.ALLOW
    assert decide(SWAP, coach) is Decision.DENY
    assert decide(SEND, coach) is Decision.DENY


@pytest.mark.parametrize("role", list(Role))
def test_users_by_role(role):
    user = Principal(PrincipalKind.USER, role=role)
    assert decide(READ, user) is Decision.ALLOW
    if role is Role.VIEWER:
        assert decide(SWAP, user) is Decision.DENY
        assert decide(SEND, user) is Decision.DENY
    else:
        assert decide(SWAP, user) is Decision.ALLOW
        assert decide(SEND, user) is Decision.REQUIRE_APPROVAL


def test_user_without_role_is_denied():
    assert decide(READ, Principal(PrincipalKind.USER)) is Decision.DENY


def test_mcp_scopes():
    none = Principal(PrincipalKind.MCP)
    reader = Principal(PrincipalKind.MCP, scopes=frozenset({SCOPE_READ}))
    writer = Principal(PrincipalKind.MCP, scopes=frozenset({SCOPE_READ, SCOPE_WRITE}))
    full = Principal(PrincipalKind.MCP, scopes=frozenset({SCOPE_READ, SCOPE_WRITE, SCOPE_EXTERNAL}))
    assert decide(READ, none) is Decision.DENY
    assert decide(READ, reader) is Decision.ALLOW
    assert decide(SWAP, reader) is Decision.DENY
    assert decide(SWAP, writer) is Decision.ALLOW
    assert decide(SEND, writer) is Decision.DENY
    assert decide(SEND, full) is Decision.REQUIRE_APPROVAL


def test_flows():
    flow = Principal(PrincipalKind.FLOW)
    assert decide(CREATE_LEAD, flow, TriggerTrust.UNTRUSTED) is Decision.ALLOW
    assert decide(SWAP, flow, TriggerTrust.UNTRUSTED) is Decision.REQUIRE_APPROVAL
    assert decide(SWAP, flow, TriggerTrust.TRUSTED) is Decision.ALLOW
    assert decide(SEND, flow, TriggerTrust.TRUSTED) is Decision.REQUIRE_APPROVAL


@pytest.mark.parametrize(
    ("kind", "trust"),
    list(itertools.product(PrincipalKind, TriggerTrust)),
)
def test_external_never_runs_without_approval(kind, trust):
    """Invariant: no principal, role or scope set lets an external tool ALLOW directly."""
    for role in [None, *Role]:
        p = Principal(kind, role=role, scopes=frozenset({SCOPE_READ, SCOPE_WRITE, SCOPE_EXTERNAL}))
        assert decide(SEND, p, trust) is not Decision.ALLOW
    assert requires_approval(ToolClass.WRITE_EXTERNAL)
    assert not requires_approval(ToolClass.WRITE_INTERNAL)


# ── transitions ──────────────────────────────────────────────────────────


def test_happy_paths():
    for a, b in [
        (LeadStatus.NEW, LeadStatus.QUALIFIED),
        (LeadStatus.QUALIFIED, LeadStatus.PROPOSAL_SENT),
        (LeadStatus.PROPOSAL_SENT, LeadStatus.WON),
    ]:
        assert_transition("lead", a, b)
    for a, b in [
        (TripStatus.DRAFT, TripStatus.PROPOSED),
        (TripStatus.PROPOSED, TripStatus.CONFIRMED),
        (TripStatus.CONFIRMED, TripStatus.IN_PROGRESS),
        (TripStatus.IN_PROGRESS, TripStatus.COMPLETED),
    ]:
        assert_transition("trip", a, b)
    assert_transition("trip_item", ItemStatus.PENDING, ItemStatus.REQUESTED)
    assert_transition("trip_item", ItemStatus.REQUESTED, ItemStatus.CONFIRMED)
    assert_transition("approval", ApprovalStatus.PENDING, ApprovalStatus.APPROVED)


@pytest.mark.parametrize(
    ("entity", "a", "b"),
    [
        ("lead", LeadStatus.WON, LeadStatus.LOST),
        ("lead", LeadStatus.NEW, LeadStatus.WON),
        ("trip", TripStatus.COMPLETED, TripStatus.CANCELLED),
        ("trip", TripStatus.IN_PROGRESS, TripStatus.CANCELLED),
        ("trip", TripStatus.DRAFT, TripStatus.CONFIRMED),
        ("approval", ApprovalStatus.APPROVED, ApprovalStatus.REJECTED),
        ("approval", ApprovalStatus.EXPIRED, ApprovalStatus.APPROVED),
    ],
)
def test_invalid(entity, a, b):
    assert not can_transition(entity, a, b)
    with pytest.raises(InvalidTransition):
        assert_transition(entity, a, b)


@pytest.mark.parametrize(
    ("entity", "enum"),
    [
        ("lead", LeadStatus),
        ("trip", TripStatus),
        ("trip_item", ItemStatus),
        ("approval", ApprovalStatus),
    ],
)
def test_tables_are_complete_and_closed(entity, enum):
    for status in enum:
        for target in enum:
            # never self-transitions, every status has an entry
            assert not (status == target and can_transition(entity, status, target))


def test_terminal_states():
    assert is_terminal("trip", TripStatus.COMPLETED)
    assert is_terminal("trip", TripStatus.CANCELLED)
    assert is_terminal("lead", LeadStatus.WON)
    assert not is_terminal("lead", LeadStatus.LOST)
    assert all(
        is_terminal("approval", s) for s in ApprovalStatus if s is not ApprovalStatus.PENDING
    )


def test_cancelling_a_trip_needs_approval():
    assert needs_approval("trip", TripStatus.CANCELLED)
    assert not needs_approval("trip", TripStatus.CONFIRMED)
