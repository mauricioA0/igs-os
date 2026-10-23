"""Postgres-backed bookkeeping for the flow interpreter: node runs, approvals, published versions.

The workflow only sees ids and small payloads; these stores make its progress visible to the API
(executions viewer, approvals inbox) and are idempotent so activity retries never duplicate rows.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import select, text
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncEngine

from igs_common.db.models import Approval, FlowExecution, FlowNodeRun, FlowVersion
from igs_common.db.session import system_scope
from igs_common.domain.approvals import payload_hash

from .types import ApprovalRequest, FlowVersionRef, NodeRunRecord

# Workflow statuses → `node_run_status`.
_NODE_STATUS = {"completed": "succeeded", "failed": "failed", "waiting": "waiting"}
# Namespace for deterministic row ids derived from (execution, node, iteration).
_NS = uuid.UUID("0b6f2c1e-3d7a-4e55-9a1d-6a0c8f2b9e10")


def node_run_key(execution_id: str, node_id: str, iteration: int) -> str:
    """Same shape as the seed (``igs_common.seed``), so a seeded waiting row is updated in place."""
    return f"{execution_id}:{node_id}:{iteration}"


def _dt(value: str | None) -> datetime | None:
    return datetime.fromisoformat(value) if value else None


async def _tenant_of(session: Any, execution_id: uuid.UUID) -> uuid.UUID:
    tenant = await session.scalar(
        select(FlowExecution.tenant_id).where(FlowExecution.id == execution_id)
    )
    if tenant is None:
        raise LookupError(f"flow execution {execution_id} not found")
    return tenant


class SqlNodeRunSink:
    def __init__(self, engine: AsyncEngine) -> None:
        self._engine = engine

    async def write(self, records: list[NodeRunRecord]) -> None:
        if not records:
            return
        async with system_scope(engine=self._engine) as s:
            tenants: dict[uuid.UUID, uuid.UUID] = {}
            for r in records:
                execution_id = uuid.UUID(r.execution_id)
                if execution_id not in tenants:
                    tenants[execution_id] = await _tenant_of(s, execution_id)
                started, ended = _dt(r.started_at), _dt(r.ended_at)
                output = r.output
                if r.output_ref is not None:
                    output = {"$ref": r.output_ref.uri, "preview": r.output_ref.preview}
                values = {
                    "id": uuid.uuid5(_NS, node_run_key(r.execution_id, r.node_id, r.iteration)),
                    "tenant_id": tenants[execution_id],
                    "execution_id": execution_id,
                    "node_id": r.node_id,
                    "node_type": r.node_type,
                    "status": _NODE_STATUS.get(r.status, r.status),
                    "output": output,
                    "error": r.error,
                    "started_at": started,
                    "finished_at": ended,
                    "duration_ms": int((ended - started).total_seconds() * 1000)
                    if started and ended
                    else None,
                    "idempotency_key": node_run_key(r.execution_id, r.node_id, r.iteration),
                }
                stmt = insert(FlowNodeRun).values(**values)
                # The seeded "waiting" row keeps its id; only its outcome changes.
                update = {
                    k: stmt.excluded[k]
                    for k in ("status", "output", "error", "finished_at", "duration_ms")
                }
                await s.execute(
                    stmt.on_conflict_do_update(index_elements=["idempotency_key"], set_=update)
                )
            # Execution status follows its latest record: an `end` node finishes it, anything
            # else means it is running again (e.g. resumed after an approval).
            for execution_id in tenants:
                last = [r for r in records if uuid.UUID(r.execution_id) == execution_id][-1]
                finished = last.node_type == "end" and last.status == "completed"
                status = (
                    "succeeded"
                    if finished
                    else ("failed" if last.status == "failed" else "running")
                )
                await s.execute(
                    text(
                        "update flow_executions set status = cast(:status as execution_status),"
                        " finished_at = case when :finished then now() else finished_at end"
                        " where id = :id"
                    ),
                    {
                        "status": status,
                        "finished": finished or status == "failed",
                        "id": execution_id,
                    },
                )


class SqlApprovals:
    """Creates the approval row an approval node waits on; returns the existing one on retry.

    An approval already pending for (execution, node) — e.g. a seeded demo approval, or the row a
    previous attempt of this activity wrote — is reused, so the inbox never shows duplicates.
    """

    def __init__(self, engine: AsyncEngine) -> None:
        self._engine = engine

    async def create(self, req: ApprovalRequest) -> str:
        execution_id = uuid.UUID(req.execution_id)
        async with system_scope(engine=self._engine) as s:
            existing = await s.scalar(
                select(Approval.id).where(
                    Approval.execution_id == execution_id,
                    Approval.node_id == req.node_id,
                    Approval.status == "pending",
                )
            )
            if existing is not None:
                return str(existing)
            tenant_id = await _tenant_of(s, execution_id)
            action = req.proposed_action or {
                "action": "approve_node",
                "params": {"node": req.node_id},
            }
            approval_id = uuid.uuid5(
                _NS, f"{req.execution_id}:{req.node_id}:{req.iteration}:{req.seq}"
            )
            stmt = insert(Approval).values(
                id=approval_id,
                tenant_id=tenant_id,
                execution_id=execution_id,
                node_id=req.node_id,
                title=req.title,
                details={"description": req.description, "links": req.links},
                proposed_action=action,
                payload_hash=payload_hash(action.get("action", ""), action.get("params", {})),
                risk_class="external" if req.proposed_action else "internal_write",
                assignee_role=str(req.assignees.get("role", "ops")),
                status="pending",
                expires_at=_dt(req.expires_at) or datetime.now(UTC),
            )
            await s.execute(stmt.on_conflict_do_nothing(index_elements=["id"]))
            return str(approval_id)


class SqlFlowVersions:
    def __init__(self, engine: AsyncEngine) -> None:
        self._engine = engine

    async def load(self, ref: FlowVersionRef) -> dict[str, Any]:
        from temporalio.exceptions import ApplicationError

        from igs_common.db.models import Flow

        async with system_scope(engine=self._engine) as s:
            q = (
                select(FlowVersion)
                .join(Flow, Flow.id == FlowVersion.flow_id)
                .where(Flow.key == ref.flow_id)
            )
            q = q.where(FlowVersion.version == ref.version) if ref.version is not None else q
            row = await s.scalar(q.order_by(FlowVersion.version.desc()).limit(1))
        if row is None:
            raise ApplicationError(
                f"flow {ref.flow_id!r} has no published version",
                type="not_found",
                non_retryable=True,
            )
        return {**row.graph, "version": row.version}
