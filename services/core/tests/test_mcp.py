"""MCP server: tool listing per scope, calls under policy, HTTP auth and resource metadata."""

import json
from collections.abc import AsyncIterator, Iterator
from contextlib import asynccontextmanager, contextmanager

import httpx
from agent_test_support import TENANT, TRIP_ID, FakeOpsBackend, principal
from mcp import Client
from pydantic import AnyHttpUrl
from starlette.applications import Starlette

from igs_core.mcp.server import build_mcp_server, current_principal
from igs_core.mcp.service import McpService, McpSettings
from igs_core.repositories import Principal, Repositories

READ_ONLY = {"igs:read"}
FULL = {"igs:read", "igs:write", "igs:external"}


@contextmanager
def as_caller(scopes: set[str]) -> Iterator[None]:
    token = current_principal.set(principal("api_key", "ops", scopes))
    try:
        yield
    finally:
        current_principal.reset(token)


async def test_listing_shows_only_what_the_key_can_call() -> None:
    server = build_mcp_server(FakeOpsBackend)
    with as_caller(READ_ONLY):
        async with Client(server) as client:
            names = {t.name for t in (await client.list_tools()).tools}
    assert {"get_trip", "get_account_brief", "search_knowledge"} <= names
    assert "update_trip_item" not in names and "send_proposal" not in names

    with as_caller(FULL):
        async with Client(server) as client:
            tools = {t.name: t for t in (await client.list_tools()).tools}
    assert {"update_trip_item", "send_proposal", "request_approval"} <= set(tools)
    hints = {name: t.annotations for name, t in tools.items()}
    assert hints["get_trip"] and hints["get_trip"].read_only_hint is True
    assert hints["cancel_trip_item"] and hints["cancel_trip_item"].destructive_hint is True
    assert hints["send_proposal"] and hints["send_proposal"].open_world_hint is True
    assert tools["get_trip"].input_schema["required"] == ["trip_id"]
    assert "decide_approval" not in tools, "approving is never exposed over MCP"


async def test_calls_run_under_policy() -> None:
    backend = FakeOpsBackend()
    server = build_mcp_server(lambda: backend)
    with as_caller(FULL):
        async with Client(server) as client:
            trip = await client.call_tool("get_trip", {"trip_id": str(TRIP_ID)})
            proposal = await client.call_tool("send_proposal", {"trip_id": str(TRIP_ID)})
    assert not trip.is_error and trip.structured_content["code"] == "IGS-2711"
    assert proposal.structured_content["status"] == "approval_required"
    [(_, request, actor)] = backend.approvals
    assert actor.surface == "mcp" and actor.type == "api_key" and request.risk_class == "external"


async def test_read_only_key_is_refused_writes() -> None:
    backend = FakeOpsBackend()
    with as_caller(READ_ONLY):
        async with Client(build_mcp_server(lambda: backend)) as client:
            result = await client.call_tool("send_proposal", {"trip_id": str(TRIP_ID)})
    assert result.is_error and result.structured_content["error"] == "not_allowed"
    assert "igs:external" in result.structured_content["message"]
    assert backend.approvals == []


async def test_unauthenticated_in_process_calls_fail() -> None:
    async with Client(build_mcp_server(FakeOpsBackend)) as client:
        assert (await client.list_tools()).tools == []
        result = await client.call_tool("get_trip", {"trip_id": str(TRIP_ID)})
    assert result.is_error and result.structured_content["error"] == "unauthenticated"


# ── Streamable HTTP + bearer auth ──────────────────────────────────────────

API_KEY = "igs_mcp_test_key"


class KeyDirectory:
    async def tenant_id_by_slug(self, slug):  # pragma: no cover - unused here
        return None

    async def principal_for_api_key(self, key_hash):
        import hashlib

        if key_hash != hashlib.sha256(API_KEY.encode()).hexdigest():
            return None
        return Principal(
            kind="api_key",
            tenant_id=TENANT,
            role="ops",
            subject="api_key:mcp",
            scopes=frozenset({"read"}),
        )

    async def ping(self):  # pragma: no cover
        return None


@asynccontextmanager
async def http_client() -> AsyncIterator[httpx.AsyncClient]:
    """Runs the session manager in the test's own task (anyio scopes can't cross tasks)."""
    repos = Repositories(directory=KeyDirectory(), trips=None, accounts=None)  # type: ignore[arg-type]
    backend = FakeOpsBackend()
    service = McpService(
        lambda: repos,
        McpSettings(
            public_url=AnyHttpUrl("http://testserver/mcp"),
            issuer_url=AnyHttpUrl("http://testserver"),
        ),
        backend=lambda: backend,
    )
    app = Starlette(routes=service.routes())
    async with service.lifespan():
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as c:
            yield c


HEADERS = {"accept": "application/json, text/event-stream", "content-type": "application/json"}


def rpc(method: str, params: dict | None = None, id_: int = 1) -> str:
    return json.dumps({"jsonrpc": "2.0", "id": id_, "method": method, "params": params or {}})


async def test_http_requires_a_valid_api_key() -> None:
    async with http_client() as http:
        await _test_http_requires_a_valid_api_key(http)


async def _test_http_requires_a_valid_api_key(http: httpx.AsyncClient) -> None:
    r = await http.post("/mcp", content=rpc("tools/list"), headers=HEADERS)
    assert r.status_code == 401
    assert "oauth-protected-resource/mcp" in r.headers["www-authenticate"]

    r = await http.post(
        "/mcp", content=rpc("tools/list"), headers=HEADERS | {"authorization": "Bearer igs_wrong"}
    )
    assert r.status_code == 401


async def test_http_resource_metadata() -> None:
    async with http_client() as http:
        await _test_http_resource_metadata(http)


async def _test_http_resource_metadata(http: httpx.AsyncClient) -> None:
    r = await http.get("/.well-known/oauth-protected-resource/mcp")
    assert r.status_code == 200
    meta = r.json()
    assert meta["resource"] == "http://testserver/mcp"
    assert set(meta["scopes_supported"]) == {"igs:read", "igs:write", "igs:external"}


async def test_http_lists_tools_for_the_key() -> None:
    async with http_client() as http:
        await _test_http_lists_tools_for_the_key(http)


async def _test_http_lists_tools_for_the_key(http: httpx.AsyncClient) -> None:
    auth = HEADERS | {"authorization": f"Bearer {API_KEY}"}
    init = await http.post(
        "/mcp",
        content=rpc(
            "initialize",
            {
                "protocolVersion": "2025-06-18",
                "capabilities": {},
                "clientInfo": {"name": "test", "version": "0"},
            },
        ),
        headers=auth,
    )
    assert init.status_code == 200, init.text
    listed = await http.post(
        "/mcp",
        content=rpc("tools/list", id_=2),
        headers=auth | {"mcp-protocol-version": "2025-06-18"},
    )
    assert listed.status_code == 200, listed.text
    names = {t["name"] for t in listed.json()["result"]["tools"]}
    assert "get_trip" in names and "update_trip_item" not in names  # legacy "read" scope only


async def test_install_mcp_on_the_core_app(settings, repos, monkeypatch) -> None:
    from igs_core.app import create_app

    monkeypatch.setenv("IGS_MCP_PUBLIC_URL", "http://test/mcp")
    app = create_app(settings, repos=repos)  # create_app installs MCP
    async with app.router.lifespan_context(app):  # runs the core lifespan + session manager
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as c:
            r = await c.post("/mcp", content=rpc("tools/list"), headers=HEADERS)
            meta = await c.get("/.well-known/oauth-protected-resource/mcp")
    assert r.status_code == 401
    assert meta.json()["resource"] == "http://test/mcp"


async def test_payment_risks_is_a_read_tool() -> None:
    backend = FakeOpsBackend()
    with as_caller(READ_ONLY):
        async with Client(build_mcp_server(lambda: backend)) as client:
            tools = {t.name: t for t in (await client.list_tools()).tools}
            result = await client.call_tool("list_payment_risks", {"within_days": 7})
    hints = tools["list_payment_risks"].annotations
    assert hints is not None and hints.read_only_hint is True
    assert not result.is_error
    assert result.structured_content["risks"][0]["outstanding_usd"] == 2280
