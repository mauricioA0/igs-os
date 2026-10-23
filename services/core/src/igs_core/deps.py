"""Request dependencies: repositories, settings and the calling principal."""

import hashlib
from typing import Annotated
from uuid import UUID

from fastapi import Depends, Request

from igs_core.config import Settings
from igs_core.errors import ProblemError
from igs_core.repositories import Principal, Repositories

API_KEY_PREFIX = "igs_"
_UNAUTHORIZED_HEADERS = {"WWW-Authenticate": 'Bearer realm="igs-os"'}


def get_settings(request: Request) -> Settings:
    return request.app.state.settings


def get_repos(request: Request) -> Repositories:
    return request.app.state.repos


def hash_api_key(key: str) -> str:
    return hashlib.sha256(key.encode()).hexdigest()


async def get_principal(
    request: Request,
    settings: Annotated[Settings, Depends(get_settings)],
    repos: Annotated[Repositories, Depends(get_repos)],
) -> Principal:
    """Resolve the tenant from the credentials — never from the request body.

    - ``Authorization: Bearer igs_…`` → API key (hashed lookup).
    - Other bearer tokens → user sessions (OIDC), not wired yet in phase 1.
    - No credentials → the public demo tenant, read-only, when ``demo_mode`` is on.
    """
    header = request.headers.get("authorization")
    if header:
        scheme, _, token = header.partition(" ")
        if scheme.lower() != "bearer" or not token:
            raise _unauthorized("Use 'Authorization: Bearer <token>'.")
        if token.startswith(API_KEY_PREFIX):
            principal = await repos.directory.principal_for_api_key(hash_api_key(token))
            if principal is None:
                raise _unauthorized("Invalid or revoked API key.")
            return principal
        raise _unauthorized("User sessions are not enabled yet; use an API key.")

    if not settings.demo_mode:
        raise _unauthorized("Credentials required.")
    tenant_id = await _demo_tenant_id(request, settings, repos)
    return Principal(kind="demo", tenant_id=tenant_id, role="viewer", subject="demo")


async def _demo_tenant_id(request: Request, settings: Settings, repos: Repositories) -> UUID:
    cached: UUID | None = getattr(request.app.state, "demo_tenant_id", None)
    if cached is not None:
        return cached
    tenant_id = await repos.directory.tenant_id_by_slug(settings.demo_tenant_slug)
    if tenant_id is None:
        raise ProblemError(503, "demo-unavailable", "The demo tenant is not seeded.")
    request.app.state.demo_tenant_id = tenant_id
    return tenant_id


def _unauthorized(detail: str) -> ProblemError:
    return ProblemError(401, "unauthorized", detail, headers=_UNAUTHORIZED_HEADERS)


CurrentPrincipal = Annotated[Principal, Depends(get_principal)]
Repos = Annotated[Repositories, Depends(get_repos)]
AppSettings = Annotated[Settings, Depends(get_settings)]
