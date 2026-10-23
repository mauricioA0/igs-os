"""Async engine and tenant-scoped sessions.

    async with session_scope(tenant_id) as session:
        session.add(Trip(...))          # committed on exit, rolled back on error

Every transaction sets `app.tenant_id` (SET LOCAL semantics), which the RLS policies read.
"""

import os
import re
import uuid
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker
from sqlalchemy.ext.asyncio import create_async_engine as _create_async_engine

from igs_common.db.rls import TENANT_GUC

_ROLE_NAME = re.compile(r"^[a-z_][a-z0-9_]*$")

_engine: AsyncEngine | None = None
_sessionmaker: async_sessionmaker[AsyncSession] | None = None


def normalize_url(url: str) -> str:
    """Accept `postgres://` / `postgresql://` URLs and force the asyncpg driver."""
    return re.sub(r"^postgres(ql)?(\+\w+)?://", "postgresql+asyncpg://", url)


def create_engine(url: str, **kwargs: object) -> AsyncEngine:
    kwargs.setdefault("pool_pre_ping", True)
    return _create_async_engine(normalize_url(url), **kwargs)  # type: ignore[arg-type]


def configure(url: str | None = None, **kwargs: object) -> AsyncEngine:
    """Set the process-wide engine (call once at startup). Defaults to $DATABASE_URL."""
    global _engine, _sessionmaker
    url = url or os.environ.get("IGS_DATABASE_URL") or os.environ.get("DATABASE_URL")
    if not url:
        raise RuntimeError("Set DATABASE_URL (or IGS_DATABASE_URL) or call configure(url)")
    _engine = create_engine(url, **kwargs)
    _sessionmaker = async_sessionmaker(_engine, expire_on_commit=False)
    return _engine


def get_engine() -> AsyncEngine:
    return _engine or configure()


def _sessions(engine: AsyncEngine | None) -> async_sessionmaker[AsyncSession]:
    if engine is not None:
        return async_sessionmaker(engine, expire_on_commit=False)
    if _sessionmaker is None:
        configure()
    assert _sessionmaker is not None
    return _sessionmaker


def _app_role(role: str | None) -> str | None:
    role = role if role is not None else os.environ.get("IGS_DB_APP_ROLE") or None
    if role is not None and not _ROLE_NAME.match(role):
        raise ValueError(f"invalid role name: {role!r}")
    return role


@asynccontextmanager
async def session_scope(
    tenant_id: uuid.UUID | str,
    *,
    engine: AsyncEngine | None = None,
    role: str | None = None,
) -> AsyncIterator[AsyncSession]:
    """One transaction bound to a tenant. Commits on success, rolls back on error.

    `role` (or $IGS_DB_APP_ROLE) switches to a non-owner role for the transaction so RLS applies
    even when the connection user is the table owner, as in local dev and tests.
    """
    tid = str(uuid.UUID(str(tenant_id)))
    app_role = _app_role(role)
    async with _sessions(engine)() as session, session.begin():
        if app_role:
            await session.execute(text(f"SET LOCAL ROLE {app_role}"))
        await session.execute(
            text("SELECT set_config(:guc, :tid, true)"), {"guc": TENANT_GUC, "tid": tid}
        )
        yield session


@asynccontextmanager
async def system_scope(*, engine: AsyncEngine | None = None) -> AsyncIterator[AsyncSession]:
    """Cross-tenant transaction as the connection role (migrations user / system workers).

    For the outbox dispatcher, tenant resolution and the seed — never for request handling.
    """
    async with _sessions(engine)() as session, session.begin():
        yield session


async def dispose() -> None:
    global _engine, _sessionmaker
    if _engine is not None:
        await _engine.dispose()
    _engine = None
    _sessionmaker = None
