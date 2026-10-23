"""Tool classes and the policy that decides whether a tool call may run.

See docs/architecture/security.md §3 (tool classes) and §4 (MCP scopes). The registry declares a
class per tool; this module decides, for a given principal and trigger, whether the call is
allowed, needs an approval first, or is denied. The server enforces it; UI/MCP hints only mirror it.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum


class ToolClass(StrEnum):
    READ = "read"
    WRITE_INTERNAL = "write-internal"
    # External side effects and destructive operations (messages, cancellations, money).
    WRITE_EXTERNAL = "write-external"


class TriggerTrust(StrEnum):
    TRUSTED = "trusted"  # an ops person, a schedule, an internal event from trusted data
    UNTRUSTED = "untrusted"  # chat, webhook, anything derived from outside text


class TriggerKind(StrEnum):
    CHAT = "chat"
    WEBHOOK = "webhook"
    SCHEDULE = "schedule"
    EVENT = "event"
    MANUAL = "manual"


class PrincipalKind(StrEnum):
    USER = "user"  # ops staff in the panel
    FLOW = "flow"  # a flow execution
    MCP = "mcp"  # an MCP client (Claude Code/Desktop, other agents)
    COACH_AGENT = "coach_agent"  # the public, coach-facing agent


class Role(StrEnum):
    OWNER = "owner"
    OPS = "ops"
    SALES = "sales"
    VIEWER = "viewer"


class Decision(StrEnum):
    ALLOW = "allow"
    REQUIRE_APPROVAL = "require_approval"
    DENY = "deny"


# MCP OAuth scopes → highest tool class they unlock.
SCOPE_READ = "igs:read"
SCOPE_WRITE = "igs:write"
SCOPE_EXTERNAL = "igs:external"


@dataclass(frozen=True)
class ToolSpec:
    name: str
    tool_class: ToolClass
    # Write-internal "propose" tools the public coach agent may call (create_lead, draft_trip).
    coach_safe: bool = False


@dataclass(frozen=True)
class Principal:
    kind: PrincipalKind
    role: Role | None = None
    scopes: frozenset[str] = field(default_factory=frozenset)


def trigger_trust(kind: TriggerKind, *, tainted: bool = False) -> TriggerTrust:
    """Chat and webhooks are untrusted. Events inherit taint from the data that produced them."""
    if kind in (TriggerKind.CHAT, TriggerKind.WEBHOOK) or tainted:
        return TriggerTrust.UNTRUSTED
    return TriggerTrust.TRUSTED


def requires_approval(tool_class: ToolClass) -> bool:
    """External/destructive tools always need an approval, whoever calls them."""
    return tool_class is ToolClass.WRITE_EXTERNAL


def decide(
    tool: ToolSpec, principal: Principal, trust: TriggerTrust = TriggerTrust.TRUSTED
) -> Decision:
    match principal.kind:
        case PrincipalKind.COACH_AGENT:
            if tool.tool_class is ToolClass.READ:
                return Decision.ALLOW
            if tool.tool_class is ToolClass.WRITE_INTERNAL and tool.coach_safe:
                return Decision.ALLOW
            return Decision.DENY

        case PrincipalKind.USER:
            if principal.role is None:
                return Decision.DENY
            if tool.tool_class is ToolClass.READ:
                return Decision.ALLOW
            if principal.role is Role.VIEWER:
                return Decision.DENY
            if tool.tool_class is ToolClass.WRITE_INTERNAL:
                return Decision.ALLOW
            return Decision.REQUIRE_APPROVAL

        case PrincipalKind.MCP:
            needed = {
                ToolClass.READ: SCOPE_READ,
                ToolClass.WRITE_INTERNAL: SCOPE_WRITE,
                ToolClass.WRITE_EXTERNAL: SCOPE_EXTERNAL,
            }[tool.tool_class]
            if needed not in principal.scopes:
                return Decision.DENY
            return (
                Decision.REQUIRE_APPROVAL if requires_approval(tool.tool_class) else Decision.ALLOW
            )

        case PrincipalKind.FLOW:
            # Internal writes from untrusted input are allowed (e.g. create_lead from chat) and
            # audited; external effects wait for an approval node regardless of the trigger.
            if requires_approval(tool.tool_class):
                return Decision.REQUIRE_APPROVAL
            if trust is TriggerTrust.UNTRUSTED and tool.tool_class is ToolClass.WRITE_INTERNAL:
                return Decision.ALLOW if tool.coach_safe else Decision.REQUIRE_APPROVAL
            return Decision.ALLOW
