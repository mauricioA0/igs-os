"""Tenant isolation is enforced by Postgres, not by remembering a WHERE clause."""

import uuid
from datetime import date

import pytest
from sqlalchemy import func, select, text, update
from sqlalchemy.exc import DBAPIError, ProgrammingError
from sqlalchemy.ext.asyncio import AsyncEngine

from igs_common.db import session_scope, system_scope, uuid7
from igs_common.db.enums import ActorType
from igs_common.db.models import ApiKey, AuditLog, Tenant, Trip
from igs_common.db.rls import APP_ROLE


async def _make_tenant(engine: AsyncEngine, slug: str) -> uuid.UUID:
    tenant_id = uuid7()
    async with system_scope(engine=engine) as s:
        s.add(Tenant(id=tenant_id, slug=f"{slug}-{tenant_id.hex[-12:]}", name=slug))
        await s.flush()
        s.add(
            Trip(
                tenant_id=tenant_id,
                title=f"{slug} tour",
                city="Buenos Aires",
                country="Argentina",
                start_date=date(2027, 3, 7),
                end_date=date(2027, 3, 16),
                price_per_person_usd=2890,
            )
        )
    return tenant_id


@pytest.fixture
async def two_tenants(engine: AsyncEngine) -> tuple[uuid.UUID, uuid.UUID]:
    return await _make_tenant(engine, "alpha"), await _make_tenant(engine, "beta")


async def test_reads_only_see_own_tenant(engine: AsyncEngine, two_tenants) -> None:
    alpha, beta = two_tenants
    async with session_scope(alpha, engine=engine, role=APP_ROLE) as s:
        tenants = set((await s.scalars(select(Trip.tenant_id))).all())
    assert tenants == {alpha}

    async with session_scope(beta, engine=engine, role=APP_ROLE) as s:
        titles = (await s.scalars(select(Trip.title))).all()
    assert titles == ["beta tour"]


async def test_cannot_write_into_another_tenant(engine: AsyncEngine, two_tenants) -> None:
    alpha, beta = two_tenants
    with pytest.raises(DBAPIError, match="row-level security"):
        async with session_scope(alpha, engine=engine, role=APP_ROLE) as s:
            s.add(
                Trip(
                    tenant_id=beta,
                    title="smuggled",
                    city="Rio de Janeiro",
                    country="Brazil",
                    start_date=date(2027, 6, 1),
                    end_date=date(2027, 6, 10),
                    price_per_person_usd=1,
                )
            )


async def test_cannot_update_another_tenants_rows(engine: AsyncEngine, two_tenants) -> None:
    alpha, beta = two_tenants
    async with session_scope(alpha, engine=engine, role=APP_ROLE) as s:
        result = await s.execute(
            update(Trip).where(Trip.tenant_id == beta).values(title="hijacked")
        )
    assert result.rowcount == 0  # type: ignore[attr-defined]

    async with session_scope(beta, engine=engine, role=APP_ROLE) as s:
        assert (await s.scalars(select(Trip.title))).all() == ["beta tour"]


async def test_missing_tenant_fails_closed(engine: AsyncEngine, two_tenants) -> None:
    async with system_scope(engine=engine) as s:
        await s.execute(text(f"SET LOCAL ROLE {APP_ROLE}"))
        count = await s.scalar(select(func.count()).select_from(Trip))
    assert count == 0


async def test_tenants_table_is_readable(engine: AsyncEngine, two_tenants) -> None:
    alpha, _ = two_tenants
    async with session_scope(alpha, engine=engine, role=APP_ROLE) as s:
        assert (await s.scalar(select(func.count()).select_from(Tenant)) or 0) >= 2


async def test_audit_log_is_append_only(engine: AsyncEngine, two_tenants) -> None:
    alpha, _ = two_tenants
    async with session_scope(alpha, engine=engine, role=APP_ROLE) as s:
        s.add(
            AuditLog(
                tenant_id=alpha,
                actor_type=ActorType.SYSTEM,
                action="test.write",
                subject_type="trip",
            )
        )

    with pytest.raises(ProgrammingError, match="permission denied"):
        async with session_scope(alpha, engine=engine, role=APP_ROLE) as s:
            await s.execute(update(AuditLog).values(action="tampered"))


async def test_api_key_lookup_crosses_tenants_only_via_function(
    engine: AsyncEngine, two_tenants
) -> None:
    alpha, _ = two_tenants
    key_hash = uuid7().hex + uuid7().hex  # 64 chars, unique per run
    async with system_scope(engine=engine) as s:
        s.add(
            ApiKey(
                tenant_id=alpha, name="mcp", hash=key_hash, prefix="igs_test", scopes=["igs:read"]
            )
        )
        s.add(
            ApiKey(
                tenant_id=alpha,
                name="revoked",
                hash=key_hash[::-1],
                prefix="igs_rev",
                revoked_at=func.now(),
            )
        )

    # No tenant set: the table itself is invisible to the app role…
    async with system_scope(engine=engine) as s:
        await s.execute(text(f"SET LOCAL ROLE {APP_ROLE}"))
        assert (await s.scalar(select(func.count()).select_from(ApiKey))) == 0
        # …but the SECURITY DEFINER function resolves an active key to its tenant.
        row = (await s.execute(text("select * from resolve_api_key(:h)"), {"h": key_hash})).one()
        assert row.tenant_id == alpha
        assert row.scopes == ["igs:read"]
        assert row.role == "viewer"
        revoked = await s.execute(text("select * from resolve_api_key(:h)"), {"h": key_hash[::-1]})
        assert revoked.first() is None
