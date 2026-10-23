"""Run one tool call under the tool-class policy (security.md §3-4).

The decision comes from `igs_common.domain.tools.decide`; this module maps API principals onto
it, validates arguments, turns write-external calls into approvals bound to a payload hash, and
returns a JSON-safe outcome. It never raises for model-caused problems: those come back as
`is_error` outcomes the model can react to.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from typing import Any, Literal

from pydantic import ValidationError

from igs_common.domain.approvals import payload_hash
from igs_common.domain.tools import (
    SCOPE_EXTERNAL,
    SCOPE_READ,
    SCOPE_WRITE,
    Decision,
    PrincipalKind,
    Role,
    ToolClass,
    ToolSpec,
    TriggerTrust,
    decide,
)
from igs_common.domain.tools import (
    Principal as PolicyPrincipal,
)
from igs_core.agent.backend import ApprovalRequest, BackendUnavailable
from igs_core.agent.tools import ToolContext, ToolDef
from igs_core.repositories.base import Principal

log = logging.getLogger(__name__)

Surface = Literal["copilot", "mcp"]

# API keys created before the igs:* scopes used the core-api.md names.
_LEGACY_SCOPES = {"read": SCOPE_READ, "write": SCOPE_WRITE, "external": SCOPE_EXTERNAL}

# approvals.risk_class values (db enum) for each domain tool class.
RISK_CLASS = {
    ToolClass.READ: "read",
    ToolClass.WRITE_INTERNAL: "internal_write",
    ToolClass.WRITE_EXTERNAL: "external",
}


def normalize_scopes(scopes: frozenset[str] | set[str] | list[str]) -> frozenset[str]:
    return frozenset(_LEGACY_SCOPES.get(s, s) for s in scopes)


def policy_principal(principal: Principal, surface: Surface) -> PolicyPrincipal:
    """MCP callers are judged by scopes; panel users (copilot) by their role."""
    if surface == "mcp":
        return PolicyPrincipal(kind=PrincipalKind.MCP, scopes=normalize_scopes(principal.scopes))
    return PolicyPrincipal(kind=PrincipalKind.USER, role=Role(principal.role))


def propose_only(principal: Principal, surface: Surface) -> bool:
    """The public demo may PROPOSE actions through the copilot (approval rows) but never run a
    write or decide an approval: deciding goes through the approvals API, which rejects demo."""
    return surface == "copilot" and principal.kind == "demo"


def actor_type(principal: Principal, surface: Surface) -> str:
    """audit_log.actor_type: MCP calls are attributed to the key, copilot calls to the agent."""
    if surface == "mcp":
        return "api_key" if principal.kind == "api_key" else "agent"
    return "agent"


@dataclass(frozen=True)
class ToolOutcome:
    output: Any
    is_error: bool = False
    decision: Decision | None = None
    approval: dict[str, Any] | None = None

    def as_text(self) -> str:
        return json.dumps(self.output, default=str, ensure_ascii=False)


async def execute_tool(
    ctx: ToolContext,
    tool: ToolDef,
    principal: PolicyPrincipal,
    arguments: dict[str, Any],
    *,
    trust: TriggerTrust = TriggerTrust.TRUSTED,
    propose_only: bool = False,
) -> ToolOutcome:
    try:
        args = tool.input_model.model_validate(arguments)
    except ValidationError as exc:
        return ToolOutcome(
            {"error": "invalid_arguments", "details": exc.errors(include_url=False)},
            is_error=True,
        )

    decision = decide(ToolSpec(tool.name, tool.tool_class), principal, trust)
    if propose_only and tool.tool_class is not ToolClass.READ:
        # Never ALLOW a write here; only tools that can describe themselves become proposals.
        decision = Decision.REQUIRE_APPROVAL if tool.propose is not None else Decision.DENY
    if decision is Decision.DENY:
        message = (
            "The public demo can read and propose actions, not change data."
            if propose_only
            else _deny_message(tool, principal)
        )
        return ToolOutcome(
            {"error": "not_allowed", "message": message},
            is_error=True,
            decision=decision,
        )

    try:
        if decision is Decision.REQUIRE_APPROVAL:
            return await _request_approval(ctx, tool, args, decision)
        if tool.handler is None:  # pragma: no cover - registry invariant
            return ToolOutcome({"error": "not_executable"}, is_error=True, decision=decision)
        return ToolOutcome(await tool.handler(ctx, args), decision=decision)
    except (LookupError, ValueError) as exc:
        return ToolOutcome(
            {"error": "failed", "message": str(exc)}, is_error=True, decision=decision
        )
    except BackendUnavailable as exc:
        return ToolOutcome(
            {"error": "unavailable", "message": str(exc)}, is_error=True, decision=decision
        )

    except Exception:  # a broken tool must not end the turn; the model gets a generic error
        log.exception("tool %s failed", tool.name)
        return ToolOutcome(
            {"error": "internal", "message": f"{tool.name} failed unexpectedly."},
            is_error=True,
            decision=decision,
        )


async def _request_approval(
    ctx: ToolContext, tool: ToolDef, args: Any, decision: Decision
) -> ToolOutcome:
    if tool.propose is None:
        # A gated tool must describe its action; never fall through to executing it.
        return ToolOutcome({"error": "approval_unsupported"}, is_error=True, decision=decision)
    proposal = await tool.propose(ctx, args)
    digest = payload_hash(tool.name, proposal.params)
    approval = await ctx.backend.create_approval(
        ctx.tenant_id,
        ApprovalRequest(
            title=proposal.title,
            action=tool.name,
            params=proposal.params,
            payload_hash=digest,
            risk_class=RISK_CLASS[tool.tool_class],
            subject_type=proposal.subject_type,
            subject_id=proposal.subject_id,
            reason=proposal.reason,
        ),
        ctx.actor,
    )
    output = {
        "status": "approval_required",
        "approval_id": str(approval["id"]),
        "title": proposal.title,
        "payload_hash": digest,
        "review_url": f"/ops/approvals?id={approval['id']}",
        "message": "Nothing was done yet. A person must approve this exact action in IGS OS.",
    }
    return ToolOutcome(output, decision=decision, approval=output)


def _deny_message(tool: ToolDef, principal: PolicyPrincipal) -> str:
    if principal.kind is PrincipalKind.MCP:
        needed = {
            ToolClass.READ: SCOPE_READ,
            ToolClass.WRITE_INTERNAL: SCOPE_WRITE,
            ToolClass.WRITE_EXTERNAL: SCOPE_EXTERNAL,
        }[tool.tool_class]
        return f"This API key lacks the {needed!r} scope required by {tool.name}."
    return f"Your role can't use {tool.name} ({tool.tool_class.value})."
