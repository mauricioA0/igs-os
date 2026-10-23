"""Postgres record stores: the seeded demo approval is reused and node runs update in place."""

import uuid
from collections.abc import AsyncIterator

import pytest
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncEngine
from sqlalchemy.pool import NullPool

from igs_common.db.models import Approval, FlowExecution, FlowNodeRun
from igs_common.db.session import create_engine, system_scope
from igs_common.seed import fixture_id, load
from igs_common.testing import DatabaseUnavailableError, database_url, prepare_database
from igs_worker.activities.records_sql import SqlApprovals, SqlNodeRunSink
from igs_worker.activities.types import ApprovalRequest, NodeRunRecord

EXECUTION = str(fixture_id("igs", "execution", "ex-lak-inbound"))
SEEDED_APPROVAL = fixture_id("igs", "approval", "a-9003")


@pytest.fixture(scope="module")
def db_url() -> str:
    try:
        prepare_database("igs_test_y6_records")
    except DatabaseUnavailableError as exc:  # pragma: no cover - env dependent
        pytest.skip(f"Postgres not available: {exc}")
    return database_url("igs_test_y6_records", driver="postgresql+asyncpg")


@pytest.fixture
async def engine(db_url: str) -> AsyncIterator[AsyncEngine]:
    eng = create_engine(db_url, poolclass=NullPool)
    async with system_scope(engine=eng) as s:
        await load(s)
    yield eng
    await eng.dispose()


async def test_pending_seeded_approval_is_reused(engine: AsyncEngine) -> None:
    req = ApprovalRequest(
        execution_id=EXECUTION,
        node_id="ops_review",
        iteration=1,
        title="Review proposal",
        description=None,
        assignees={"role": "ops"},
        expires_at="2026-10-24T11:10:00+00:00",
    )
    store = SqlApprovals(engine)
    assert await store.create(req) == str(SEEDED_APPROVAL)
    assert await store.create(req) == str(SEEDED_APPROVAL)  # retried activity
    async with system_scope(engine=engine) as s:
        count = await s.scalar(
            select(func.count())
            .select_from(Approval)
            .where(Approval.execution_id == uuid.UUID(EXECUTION))
        )
    assert count == 1


async def test_node_runs_update_in_place_and_finish_the_execution(engine: AsyncEngine) -> None:
    def record(node: str, node_type: str, port: str | None) -> NodeRunRecord:
        return NodeRunRecord(
            execution_id=EXECUTION,
            node_id=node,
            node_type=node_type,
            iteration=1,
            status="completed",
            port=port,
            started_at="2026-10-22T12:00:00+00:00",
            ended_at="2026-10-22T12:00:01+00:00",
            output={"ok": True},
        )

    sink = SqlNodeRunSink(engine)
    await sink.write([record("ops_review", "approval", "approved")])
    await sink.write([record("done", "end", None)])
    async with system_scope(engine=engine) as s:
        rows = (
            await s.scalars(
                select(FlowNodeRun).where(
                    FlowNodeRun.execution_id == uuid.UUID(EXECUTION),
                    FlowNodeRun.node_id == "ops_review",
                )
            )
        ).all()
        execution = await s.get(FlowExecution, uuid.UUID(EXECUTION))
    assert [r.status for r in rows] == ["succeeded"]  # the seeded waiting row, not a duplicate
    assert execution is not None and execution.status == "succeeded"
    assert execution.finished_at is not None
