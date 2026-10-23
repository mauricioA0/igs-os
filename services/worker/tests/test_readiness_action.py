"""The `check_trip_readiness` flow action against the seeded Rio roster (real Postgres, RLS)."""

from collections.abc import AsyncIterator

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncEngine
from sqlalchemy.pool import NullPool

from igs_common.db.models import Tenant
from igs_common.db.session import create_engine, system_scope
from igs_common.domain.tools import ToolClass
from igs_common.seed import fixture_id, load
from igs_common.testing import DatabaseUnavailableError, database_url, prepare_database
from igs_worker.domain_actions import (
    ActionContext,
    ActionError,
    SqlDomainActions,
    action_tool_class,
)

RIO = str(fixture_id("igs", "trip", "t-2715"))


@pytest.fixture(scope="module")
def db_url() -> str:
    try:
        prepare_database("igs_test_y6_readiness")
    except DatabaseUnavailableError as exc:  # pragma: no cover - env dependent
        pytest.skip(f"Postgres not available: {exc}")
    return database_url("igs_test_y6_readiness", driver="postgresql+asyncpg")


@pytest.fixture
async def engine(db_url: str) -> AsyncIterator[AsyncEngine]:
    eng = create_engine(db_url, poolclass=NullPool)
    async with system_scope(engine=eng) as s:
        await load(s)
    yield eng
    await eng.dispose()


async def _ctx(engine: AsyncEngine) -> ActionContext:
    async with system_scope(engine=engine) as s:
        tenant = (await s.scalars(select(Tenant.id).where(Tenant.slug == "igs"))).one()
    return ActionContext(tenant_id=str(tenant), execution_id="ex-1", node_id="check", iteration=0)


def test_readiness_is_a_read_action() -> None:
    assert action_tool_class("check_trip_readiness") is ToolClass.READ


async def test_check_reports_the_open_documents(engine: AsyncEngine) -> None:
    actions = SqlDomainActions(engine=engine)
    out = await actions.run("check_trip_readiness", {"tripId": RIO}, await _ctx(engine))
    assert out["ready"] is False
    assert out["travelers"] == 22
    assert out["rulesVersion"] == "2026-10"
    names = {p["name"] for p in out["notReady"]}
    assert "Paul Lindgren" in names  # passport expires mid-trip
    assert out["summary"].startswith(f"{out['travelersReady']}/22 travelers ready")


async def test_unknown_trip_is_not_found(engine: AsyncEngine) -> None:
    actions = SqlDomainActions(engine=engine)
    with pytest.raises(ActionError):
        await actions.run(
            "check_trip_readiness",
            {"tripId": "00000000-0000-0000-0000-000000000000"},
            await _ctx(engine),
        )
