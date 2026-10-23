"""`list_payment_risks` on the SQL backend against the seeded demo (Lakeshore's enrollment)."""

from collections.abc import AsyncIterator
from typing import Any

import pytest
from sqlalchemy.ext.asyncio import AsyncEngine
from sqlalchemy.pool import NullPool

from igs_common.db.session import create_engine, session_scope, system_scope
from igs_common.seed import fixture_id, load
from igs_common.testing import DatabaseUnavailableError, database_url, prepare_database
from igs_core.agent.backend import SqlOpsBackend

DB = "igs_test_c5_core"
TENANT = fixture_id("igs", "tenant", "igs")
LAKESHORE = fixture_id("igs", "account", "acc-lakeshore")


@pytest.fixture(scope="module")
def db_url() -> str:
    try:
        prepare_database(DB)
    except DatabaseUnavailableError as exc:  # pragma: no cover - env dependent
        pytest.skip(f"Postgres not available: {exc}")
    return database_url(DB, driver="postgresql+asyncpg")


@pytest.fixture
async def engine(db_url: str) -> AsyncIterator[AsyncEngine]:
    eng = create_engine(db_url, poolclass=NullPool)
    async with system_scope(engine=eng) as s:
        await load(s)
    yield eng
    await eng.dispose()


async def test_lakeshore_enrollment_is_the_top_risk(engine: AsyncEngine) -> None:
    backend = SqlOpsBackend(
        lambda tenant: session_scope(tenant, engine=engine),
        trips=None,  # type: ignore[arg-type]
        accounts=None,  # type: ignore[arg-type]
    )
    out: dict[str, Any] = await backend.list_payment_risks(
        TENANT, account_id=LAKESHORE, trip_id=None, within_days=14, limit=10
    )
    (risk,) = out["risks"]
    assert risk["trip_code"] == "IGS-2711" and risk["kind"] == "enrollment"
    assert risk["seats"] == 24 and risk["outstanding_usd"] == 2280
    assert risk["days"] < 0 and risk["recipient"] == "Dana Whitfield"
    assert out["overdue_usd"] == 2280 and out["truncated"] is False
