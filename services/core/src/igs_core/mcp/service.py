"""Streamable HTTP wiring for the MCP server, mountable on the core FastAPI app.

- Stateless Streamable HTTP at `/mcp` (JSON responses), so any core replica can serve any call.
- Bearer auth with IGS API keys (`igs_…`, scopes igs:read / igs:write / igs:external). The token
  is verified per request; the tenant comes from the key, never from the client.
- OAuth 2.1 resource-server metadata (RFC 9728) at
  `/.well-known/oauth-protected-resource/mcp`, so spec-following clients discover where tokens
  come from. The authorization server itself is a later phase; until then it's a stub issuer.

Usage in `app.py` (one line, after the app and its lifespan are created):

    install_mcp(app)

It adds the `/mcp` route and the metadata route, and wraps the app lifespan so the session
manager's task group runs for the app's lifetime. (A plain `app.mount("/mcp", …)` would not run
it: Starlette doesn't run lifespans of mounted apps.)
"""

from __future__ import annotations

import hashlib
from collections.abc import AsyncIterator, Callable
from contextlib import AbstractAsyncContextManager, asynccontextmanager
from typing import Any

from mcp.server.auth.middleware.auth_context import AuthContextMiddleware
from mcp.server.auth.middleware.bearer_auth import BearerAuthBackend, RequireAuthMiddleware
from mcp.server.auth.provider import AccessToken
from mcp.server.auth.routes import build_resource_metadata_url, create_protected_resource_routes
from mcp.server.streamable_http_manager import StreamableHTTPASGIApp, StreamableHTTPSessionManager
from mcp.server.transport_security import TransportSecuritySettings
from pydantic import AnyHttpUrl
from pydantic_settings import BaseSettings, SettingsConfigDict
from starlette.applications import Starlette
from starlette.middleware.authentication import AuthenticationMiddleware
from starlette.routing import BaseRoute, Route

from igs_common.domain.tools import SCOPE_EXTERNAL, SCOPE_READ, SCOPE_WRITE
from igs_common.rag import search_knowledge
from igs_core import db
from igs_core.agent.backend import OpsBackend, SqlOpsBackend
from igs_core.agent.policy import normalize_scopes
from igs_core.mcp.server import build_mcp_server
from igs_core.repositories import Repositories

API_KEY_PREFIX = "igs_"
SCOPES = [SCOPE_READ, SCOPE_WRITE, SCOPE_EXTERNAL]


class McpSettings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="IGS_MCP_", env_file=".env", extra="ignore")

    # Public URL of the MCP endpoint (the OAuth "resource"). Must match what clients connect to.
    public_url: AnyHttpUrl = AnyHttpUrl("http://localhost:8000/mcp")
    # Authorization server advertised in the resource metadata (stub until OAuth ships).
    issuer_url: AnyHttpUrl = AnyHttpUrl("http://localhost:8000")
    # DNS-rebinding protection (validates Host/Origin). Behind Cloud Run set the public host.
    allowed_hosts: list[str] = ["localhost:*", "127.0.0.1:*", "testserver"]
    allowed_origins: list[str] = ["http://localhost:*", "http://127.0.0.1:*"]
    dns_rebinding_protection: bool = True


class ApiKeyVerifier:
    """`TokenVerifier` for IGS API keys: sha256 lookup through the API's directory."""

    def __init__(self, repos: Callable[[], Repositories], resource: str) -> None:
        self._repos = repos
        self._resource = resource

    async def verify_token(self, token: str) -> AccessToken | None:
        if not token.startswith(API_KEY_PREFIX):
            return None
        key_hash = hashlib.sha256(token.encode()).hexdigest()
        principal = await self._repos().directory.principal_for_api_key(key_hash)
        if principal is None:
            return None
        return AccessToken(
            token=token,
            client_id=principal.subject,
            subject=principal.subject,
            scopes=sorted(normalize_scopes(principal.scopes)),
            resource=self._resource,
            claims={"tenant_id": str(principal.tenant_id), "role": principal.role},
        )


class McpService:
    def __init__(
        self,
        repos: Callable[[], Repositories],
        settings: McpSettings | None = None,
        *,
        backend: Callable[[], OpsBackend] | None = None,
    ) -> None:
        self.settings = settings or McpSettings()
        resource = str(self.settings.public_url)

        def default_backend() -> OpsBackend:
            r = repos()
            return SqlOpsBackend(db.tenant_session, r.trips, r.accounts, knowledge=search_knowledge)

        self.server = build_mcp_server(backend or default_backend)
        self.session_manager = StreamableHTTPSessionManager(
            app=self.server,
            json_response=True,
            stateless=True,
            security_settings=TransportSecuritySettings(
                enable_dns_rebinding_protection=self.settings.dns_rebinding_protection,
                allowed_hosts=self.settings.allowed_hosts,
                allowed_origins=self.settings.allowed_origins,
            ),
        )
        self.metadata_url = build_resource_metadata_url(self.settings.public_url)
        protected = RequireAuthMiddleware(
            StreamableHTTPASGIApp(self.session_manager), [SCOPE_READ], self.metadata_url
        )
        self.asgi: Any = AuthenticationMiddleware(
            AuthContextMiddleware(protected),
            backend=BearerAuthBackend(ApiKeyVerifier(repos, resource)),
        )

    @classmethod
    def from_settings(cls, repos: Callable[[], Repositories]) -> McpService:
        return cls(repos, McpSettings())

    def routes(self, path: str = "/mcp") -> list[BaseRoute]:
        return [
            Route(path, endpoint=self.asgi, methods=["GET", "POST", "DELETE"]),
            *create_protected_resource_routes(
                resource_url=self.settings.public_url,
                authorization_servers=[self.settings.issuer_url],
                scopes_supported=SCOPES,
                resource_name="IGS OS",
            ),
        ]

    def lifespan(self) -> AbstractAsyncContextManager[None]:
        """Must wrap the app's lifetime: runs the session manager's task group (once)."""
        return self.session_manager.run()


def install_mcp(app: Starlette, settings: McpSettings | None = None) -> McpService:
    """Add MCP routes to `app` and run the session manager inside the app's lifespan."""
    service = McpService(lambda: app.state.repos, settings)
    app.router.routes.extend(service.routes())
    inner = app.router.lifespan_context

    @asynccontextmanager
    async def lifespan(target: Any) -> AsyncIterator[Any]:
        async with inner(target) as state, service.lifespan():
            yield state

    app.router.lifespan_context = lifespan
    app.state.mcp = service
    return service
