"""The MCP server: lists the shared tool catalog and runs calls under the scope policy.

Tools come from `igs_core.agent.tools` — the same definitions the copilot uses — so behavior
can't drift between "Claude Code operating IGS" and our own agents. Write-external tools never
execute over MCP: they return `approval_required` with a link, and approving stays human.
"""

from __future__ import annotations

import contextvars
import json
from collections.abc import Callable, Sequence
from typing import Any
from uuid import UUID

import mcp_types as types
from mcp.server import Server
from mcp.server.auth.middleware.auth_context import get_access_token
from mcp.server.auth.middleware.bearer_auth import AuthenticatedUser
from mcp.server.auth.provider import AccessToken
from mcp.server.context import ServerRequestContext

from igs_common.domain.tools import SCOPE_EXTERNAL, SCOPE_READ, SCOPE_WRITE, ToolClass
from igs_core.agent.backend import Actor, OpsBackend
from igs_core.agent.policy import actor_type, execute_tool, normalize_scopes, policy_principal
from igs_core.agent.tools import TOOLS, ToolContext, ToolDef
from igs_core.repositories.base import Principal

INSTRUCTIONS = (
    "Operate Infinity Global Sports tours: trips, provider confirmations, client accounts "
    "(Account 360) and automation flows. Reads are free; internal updates are audited; anything "
    "customer-facing or destructive returns `approval_required` — a person approves it in IGS OS."
)

_SCOPE_FOR = {
    ToolClass.READ: SCOPE_READ,
    ToolClass.WRITE_INTERNAL: SCOPE_WRITE,
    ToolClass.WRITE_EXTERNAL: SCOPE_EXTERNAL,
}

# Tests (and in-process callers) can set the caller directly instead of going through HTTP auth.
current_principal: contextvars.ContextVar[Principal | None] = contextvars.ContextVar(
    "igs_mcp_principal", default=None
)

BackendProvider = Callable[[], OpsBackend]


def principal_from_token(token: AccessToken) -> Principal:
    claims = token.claims or {}
    return Principal(
        kind="api_key",
        tenant_id=UUID(str(claims["tenant_id"])),
        role=claims.get("role", "viewer"),
        subject=token.subject or token.client_id,
        scopes=normalize_scopes(token.scopes),
    )


def resolve_principal(ctx: ServerRequestContext[Any, Any]) -> Principal | None:
    if (principal := current_principal.get()) is not None:
        return principal
    token = get_access_token()
    if token is None and ctx.request is not None:
        user = getattr(ctx.request, "scope", {}).get("user")
        if isinstance(user, AuthenticatedUser):
            token = user.access_token
    return principal_from_token(token) if token is not None else None


def tool_listing(tool: ToolDef) -> types.Tool:
    return types.Tool(
        name=tool.name,
        description=tool.description,
        input_schema=tool.input_model.model_json_schema(),
        annotations=types.ToolAnnotations(
            read_only_hint=tool.tool_class is ToolClass.READ,
            destructive_hint=tool.destructive,
            idempotent_hint=tool.idempotent or tool.tool_class is ToolClass.READ,
            open_world_hint=tool.open_world,
        ),
    )


def build_mcp_server(
    backend: BackendProvider, tools: Sequence[ToolDef] = TOOLS, *, name: str = "igs-os"
) -> Server[Any]:
    by_name = {t.name: t for t in tools}

    async def on_list_tools(
        ctx: ServerRequestContext[Any, Any], _params: types.PaginatedRequestParams | None
    ) -> types.ListToolsResult:
        principal = resolve_principal(ctx)
        scopes = principal.scopes if principal else frozenset()
        # Only advertise what this key could actually call.
        visible = [t for t in tools if _SCOPE_FOR[t.tool_class] in scopes]
        return types.ListToolsResult(tools=[tool_listing(t) for t in visible])

    async def on_call_tool(
        ctx: ServerRequestContext[Any, Any], params: types.CallToolRequestParams
    ) -> types.CallToolResult:
        principal = resolve_principal(ctx)
        if principal is None:
            return _error({"error": "unauthenticated"})
        tool = by_name.get(params.name)
        if tool is None:
            return _error({"error": "unknown_tool", "name": params.name})
        tool_ctx = ToolContext(
            tenant_id=principal.tenant_id,
            actor=Actor(type=actor_type(principal, "mcp"), id=principal.subject, surface="mcp"),
            backend=backend(),
        )
        outcome = await execute_tool(
            tool_ctx, tool, policy_principal(principal, "mcp"), dict(params.arguments or {})
        )
        return types.CallToolResult(
            content=[types.TextContent(type="text", text=outcome.as_text())],
            structured_content=outcome.output if isinstance(outcome.output, dict) else None,
            is_error=outcome.is_error,
        )

    return Server(
        name,
        version="0.1.0",
        title="IGS OS",
        instructions=INSTRUCTIONS,
        on_list_tools=on_list_tools,
        on_call_tool=on_call_tool,
    )


def _error(payload: dict[str, Any]) -> types.CallToolResult:
    return types.CallToolResult(
        content=[types.TextContent(type="text", text=json.dumps(payload))],
        structured_content=payload,
        is_error=True,
    )
