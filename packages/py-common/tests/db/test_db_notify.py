"""Migration 0004: node-run and execution-status changes NOTIFY the executions SSE."""

import asyncio

import asyncpg
from sqlalchemy import update
from sqlalchemy.ext.asyncio import AsyncEngine

from igs_common.db import system_scope, uuid7
from igs_common.db.enums import ExecutionStatus, NodeRunStatus, TriggerKind
from igs_common.db.models import Flow, FlowExecution, FlowNodeRun, FlowVersion, Tenant

CHANNEL = "igs_node_runs"


async def _execution(engine: AsyncEngine) -> tuple:
    tenant_id, flow_id, version_id, execution_id = uuid7(), uuid7(), uuid7(), uuid7()
    async with system_scope(engine=engine) as s:
        s.add(Tenant(id=tenant_id, slug=f"notify-{tenant_id.hex[-12:]}", name="notify"))
        await s.flush()
        s.add(Flow(id=flow_id, tenant_id=tenant_id, key="f", name="f", draft_graph={}))
        await s.flush()
        s.add(
            FlowVersion(
                id=version_id,
                tenant_id=tenant_id,
                flow_id=flow_id,
                version=1,
                graph={},
                graph_hash="0" * 64,
                schema_version="1",
            )
        )
        await s.flush()
        s.add(
            FlowExecution(
                id=execution_id,
                tenant_id=tenant_id,
                flow_version_id=version_id,
                trigger_kind=TriggerKind.MANUAL,
                status=ExecutionStatus.RUNNING,
                temporal_workflow_id=f"man-{execution_id}",
            )
        )
    return tenant_id, execution_id


async def test_node_run_and_status_changes_notify(engine: AsyncEngine, migrated: str) -> None:
    tenant_id, execution_id = await _execution(engine)
    heard: asyncio.Queue[str] = asyncio.Queue()
    conn = await asyncpg.connect(migrated.replace("postgresql+asyncpg://", "postgresql://"))
    try:
        await conn.add_listener(CHANNEL, lambda *args: heard.put_nowait(args[3]))
        async with system_scope(engine=engine) as s:
            s.add(
                FlowNodeRun(
                    tenant_id=tenant_id,
                    execution_id=execution_id,
                    node_id="greet",
                    node_type="say",
                    status=NodeRunStatus.SUCCEEDED,
                    idempotency_key=f"{execution_id}:greet:1",
                )
            )
        assert await asyncio.wait_for(heard.get(), 5) == str(execution_id)

        async with system_scope(engine=engine) as s:
            await s.execute(
                update(FlowExecution)
                .where(FlowExecution.id == execution_id)
                .values(status=ExecutionStatus.SUCCEEDED)
            )
        assert await asyncio.wait_for(heard.get(), 5) == str(execution_id)
    finally:
        await conn.close()
