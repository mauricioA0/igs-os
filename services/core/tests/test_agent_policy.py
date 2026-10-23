"""Tool-class policy as applied to real tool calls: who may read, write, or only propose."""

from typing import Any

import pytest
from agent_test_support import ITEM_ID, TENANT, TRIP_ID, FakeOpsBackend, principal

from igs_common.domain.approvals import payload_hash, verify_payload
from igs_common.domain.tools import ToolClass
from igs_core.agent.backend import Actor
from igs_core.agent.policy import execute_tool, normalize_scopes, policy_principal
from igs_core.agent.tools import TOOLS, TOOLS_BY_NAME, ToolContext

READ_CALL = ("get_trip", {"trip_id": str(TRIP_ID)})
WRITE_CALL = ("update_trip_item", {"item_id": str(ITEM_ID), "status": "confirmed"})
EXTERNAL_CALL = ("send_proposal", {"trip_id": str(TRIP_ID), "message": "Here it is"})


def ctx(backend: FakeOpsBackend) -> ToolContext:
    return ToolContext(TENANT, Actor("agent", "test", "copilot"), backend)


async def run(backend: FakeOpsBackend, who: Any, call: tuple[str, dict[str, Any]]):
    name, args = call
    return await execute_tool(ctx(backend), TOOLS_BY_NAME[name], who, args)


MCP = "mcp"
COPILOT = "copilot"

# (surface, role, scopes) → expected outcome for (read, internal write, external write)
MATRIX = [
    (MCP, "ops", {"igs:read"}, ("ok", "denied", "denied")),
    (MCP, "ops", {"igs:read", "igs:write"}, ("ok", "ok", "denied")),
    (MCP, "ops", {"igs:read", "igs:write", "igs:external"}, ("ok", "ok", "approval")),
    (MCP, "ops", {"read", "write"}, ("ok", "ok", "denied")),  # legacy scope names
    (MCP, "owner", set(), ("denied", "denied", "denied")),  # role never stands in for scopes
    (COPILOT, "viewer", set(), ("ok", "denied", "denied")),
    (COPILOT, "sales", set(), ("ok", "ok", "approval")),
    (COPILOT, "ops", set(), ("ok", "ok", "approval")),
    (COPILOT, "owner", set(), ("ok", "ok", "approval")),
]


def kind_of(outcome: Any) -> str:
    if outcome.approval is not None:
        return "approval"
    if outcome.is_error and outcome.output.get("error") == "not_allowed":
        return "denied"
    assert not outcome.is_error, outcome.output
    return "ok"


@pytest.mark.parametrize(("surface", "role", "scopes", "expected"), MATRIX)
async def test_policy_matrix(surface, role, scopes, expected) -> None:
    who = policy_principal(principal("api_key", role, scopes), surface)
    got = []
    for call in (READ_CALL, WRITE_CALL, EXTERNAL_CALL):
        backend = FakeOpsBackend()
        got.append(kind_of(await run(backend, who, call)))
    assert tuple(got) == expected


async def test_external_write_never_executes_and_binds_payload_hash() -> None:
    backend = FakeOpsBackend()
    who = policy_principal(principal("user", "ops"), COPILOT)
    outcome = await run(backend, who, EXTERNAL_CALL)

    assert outcome.output["status"] == "approval_required"
    assert outcome.output["review_url"].startswith("/ops/approvals?id=")
    [(_, request, actor)] = backend.approvals
    assert request.action == "send_proposal"
    assert request.risk_class == "external"
    assert request.subject_type == "trip"
    assert request.payload_hash == payload_hash("send_proposal", request.params)
    assert verify_payload(outcome.output["payload_hash"], "send_proposal", request.params)
    assert actor.surface == "copilot"
    # Nothing customer-facing happened: no item/trip mutation either.
    assert backend.updates == []


async def test_internal_write_runs_and_is_attributed() -> None:
    backend = FakeOpsBackend()
    who = policy_principal(principal("user", "ops"), COPILOT)
    outcome = await run(backend, who, WRITE_CALL)
    assert outcome.output["status"] == "confirmed"
    [(item_id, actor)] = backend.updates
    assert item_id == ITEM_ID and actor.type == "agent"


async def test_invalid_arguments_are_errors_for_the_model() -> None:
    who = policy_principal(principal("user", "ops"), COPILOT)
    outcome = await run(FakeOpsBackend(), who, ("get_trip", {"trip_id": "not-a-uuid"}))
    assert outcome.is_error and outcome.output["error"] == "invalid_arguments"
    extra = await run(FakeOpsBackend(), who, ("get_trip", {"trip_id": str(TRIP_ID), "x": 1}))
    assert extra.is_error, "unknown fields are rejected"


async def test_lookup_failures_are_errors_not_exceptions() -> None:
    who = policy_principal(principal("user", "ops"), COPILOT)
    missing = "00000000-0000-0000-0000-000000000000"
    outcome = await run(FakeOpsBackend(), who, ("get_trip", {"trip_id": missing}))
    assert outcome.is_error and "not found" in outcome.output["message"]


def test_every_external_tool_can_only_propose() -> None:
    for tool in TOOLS:
        if tool.tool_class is ToolClass.WRITE_EXTERNAL:
            assert tool.handler is None and tool.propose is not None, tool.name
        else:
            assert tool.handler is not None and tool.propose is None, tool.name


def test_scope_normalization() -> None:
    assert normalize_scopes({"read", "igs:write"}) == {"igs:read", "igs:write"}
