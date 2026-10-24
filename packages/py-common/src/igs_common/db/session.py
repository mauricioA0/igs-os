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


async def verify_rls_enforced(
    *, engine: AsyncEngine | None = None, role: str | None = None, probe_table: str = "trips"
) -> None:
    """Fail-closed startup assertion that row-level security is actually in force.

    `config` already requires IGS_DB_APP_ROLE in production, but a set env var only means
    `session_scope` *attempts* to switch role — it doesn't prove RLS bites. RLS is silently
    bypassed when the effective role is a superuser, has BYPASSRLS, or owns the table. This runs
    as the same app role `session_scope` uses and asserts none of those hold, and that the role
    genuinely cannot read a tenant-scoped table with no tenant GUC set. If it can't be enforced,
    we raise at boot rather than leak across tenants at request time.

    No-ops when no app role is configured (pure-superuser local/test where RLS can't apply anyway).
    """
    app_role = _app_role(role)
    if not app_role:
        return
    async with _sessions(engine)() as session, session.begin():
        await session.execute(text(f"SET LOCAL ROLE {app_role}"))

        # 1. The effective role must not be able to bypass RLS wholesale.
        superuser = (
            await session.execute(text("SELECT current_setting('is_superuser')"))
        ).scalar_one()
        if superuser == "on":
            raise RuntimeError(f"RLS cannot be enforced: role {app_role!r} is a superuser")
        bypass = (
            await session.execute(
                text("SELECT rolbypassrls FROM pg_roles WHERE rolname = current_user")
            )
        ).scalar_one()
        if bypass:
            raise RuntimeError(f"RLS cannot be enforced: role {app_role!r} has BYPASSRLS")

        # 2. Data-independent catalog proof over EVERY RLS-enabled public table (not just one
        #    probe, and not dependent on any table holding rows). Policies are PERMISSIVE and not
        #    FORCEd, so the table owner — or any role with the owner's privileges — bypasses RLS.
        n_rls = (
            await session.execute(
                text(
                    "SELECT count(*) FROM pg_class c JOIN pg_namespace n ON n.oid = c.relnamespace "
                    "WHERE n.nspname = 'public' AND c.relkind = 'r' AND c.relrowsecurity"
                )
            )
        ).scalar_one()
        if not n_rls:
            raise RuntimeError("RLS not enforced: no public table has row level security enabled")

        # pg_has_role catches owner-privilege via role *membership*, not only literal ownership —
        # the real bypass condition Postgres checks (check_enable_rls → has_privs_of_role).
        owned = (
            await session.execute(
                text(
                    "SELECT string_agg(c.relname, ', ') FROM pg_class c "
                    "JOIN pg_namespace n ON n.oid = c.relnamespace "
                    "WHERE n.nspname = 'public' AND c.relkind = 'r' AND c.relrowsecurity "
                    "AND pg_has_role(current_user, c.relowner, 'USAGE')"
                )
            )
        ).scalar_one_or_none()
        if owned:
            raise RuntimeError(
                f"RLS cannot be enforced: role {app_role!r} has owner privileges on RLS tables "
                f"(bypasses RLS): {owned}"
            )

        # Every RLS table must carry a policy; one with RLS on and no policy is a misconfig
        # (fails closed for the app role, so it would break reads rather than leak — still caught).
        unprotected = (
            await session.execute(
                text(
                    "SELECT string_agg(c.relname, ', ') FROM pg_class c "
                    "JOIN pg_namespace n ON n.oid = c.relnamespace "
                    "WHERE n.nspname = 'public' AND c.relkind = 'r' AND c.relrowsecurity "
                    "AND NOT EXISTS (SELECT 1 FROM pg_policy p WHERE p.polrelid = c.oid)"
                )
            )
        ).scalar_one_or_none()
        if unprotected:
            raise RuntimeError(f"RLS misconfigured: RLS tables with no policy: {unprotected}")

        # 3. Cheap behavioral backstop: with no tenant GUC set, the probe table must return no rows.
        #    (Only meaningful when it holds rows; the catalog proof above is the real guarantee.)
        if probe_table:
            leaked = (
                await session.execute(text(f"SELECT count(*) FROM {probe_table}"))  # noqa: S608
            ).scalar_one()
            if leaked:
                raise RuntimeError(
                    f"RLS not enforced: read {leaked} {probe_table!r} rows with no tenant set"
                )


async def dispose() -> None:
    global _engine, _sessionmaker
    if _engine is not None:
        await _engine.dispose()
    _engine = None
    _sessionmaker = None
