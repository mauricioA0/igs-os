"""Readiness through SqlOpsBackend against the seeded demo tenant (RLS on): the Rio roster story,
an audited status update, and tenant isolation.

Needs `docker compose up -d db`; the session fixture in conftest migrates igs_test_r6. Skipped
when the database is not reachable.
"""

import os
from collections.abc import AsyncIterator
from uuid import UUID, uuid4

import pytest
from sqlalchemy import text

from igs_common.db import session as shared
from igs_common.seed import fixture_id
from igs_common.seed import load as seed_load
from igs_core.agent.backend import Actor, SqlOpsBackend
from igs_core.repositories.sql import SqlAccounts, SqlTrips

URL = os.environ.get(
    "IGS_TEST_R6_DATABASE_URL", "postgresql+asyncpg://igs:igs@localhost:5433/igs_test_r6"
)
pytestmark = pytest.mark.asyncio(loop_scope="session")
RIO = fixture_id("igs", "trip", "t-2715")
LATE_PLAYER = fixture_id("igs", "traveler", "t-2715-p19")


@pytest.fixture(scope="module")
async def env() -> AsyncIterator[tuple[SqlOpsBackend, UUID]]:
    engine = shared.configure(URL)
    try:
        async with engine.connect() as conn:
            exists = await conn.scalar(text("select to_regclass('public.traveler_documents')"))
    except OSError:
        await shared.dispose()
        pytest.skip("Postgres not reachable")
    if exists is None:
        await shared.dispose()
        pytest.skip("database not migrated")
    async with shared.system_scope() as session:
        await seed_load(session)
        tenant = (
            await session.execute(text("select id from tenants where slug = 'igs'"))
        ).scalar_one()
    os.environ["IGS_DB_APP_ROLE"] = "igs_app"
    sessions = shared.session_scope
    backend = SqlOpsBackend(sessions, SqlTrips(sessions), SqlAccounts(sessions))
    yield backend, tenant
    os.environ.pop("IGS_DB_APP_ROLE", None)
    await shared.dispose()


async def test_rio_report(env: tuple[SqlOpsBackend, UUID]) -> None:
    backend, tenant = env
    report = await backend.trip_readiness(tenant, RIO)
    assert report is not None
    assert report["trip"]["code"] == "IGS-2715" and report["travelers"] == 22
    assert report["ready"] is False
    assert "Paul Lindgren" in {p["full_name"] for p in report["not_ready"]}
    assert await backend.trip_readiness(tenant, uuid4()) is None
    assert await backend.trip_readiness(uuid4(), RIO) is None  # other tenant: RLS hides it


async def test_update_is_audited(env: tuple[SqlOpsBackend, UUID]) -> None:
    backend, tenant = env
    actor = Actor(type="agent", id="copilot-test", surface="mcp")
    row = await backend.update_traveler_document(
        tenant,
        LATE_PLAYER,
        "br_evisa",
        status="requested",
        valid_from=None,
        valid_until=None,
        note="Parents filling the VFS form",
        actor=actor,
    )
    assert row is not None and row["status"] == "requested"
    async with shared.system_scope() as session:
        audit = (
            await session.execute(
                text(
                    "select before->>'status', after->>'status' from audit_log "
                    "where action = 'traveler_document.update' and subject_id = :id "
                    "order by at desc limit 1"
                ),
                {"id": LATE_PLAYER},
            )
        ).one()
    assert tuple(audit) == ("missing", "requested")
