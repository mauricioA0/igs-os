"""Flow executions: start manual/test runs, list, inspect and stream node-run updates.

The execution row is written first (status ``running``) and committed; the workflow is started
after, with the deterministic id ``man-{execution_id}``. If Temporal is unreachable the row is
marked ``failed`` with the reason, so the panel never shows a run that does not exist.

``GET /executions/{id}/stream`` is Server-Sent Events: a ``snapshot`` first, then one
``node_run`` event per new or updated node run, and ``end`` once the execution is terminal.
It wakes on ``NOTIFY igs_node_runs '<execution_id>'`` and otherwise polls every 2 s.
"""

import asyncio
import json
from collections.abc import AsyncIterator
from datetime import UTC, datetime
from typing import Annotated, Any
from uuid import UUID

import structlog
from fastapi import APIRouter, Query, Request
from sqlalchemy import select, tuple_
from sse_starlette.sse import EventSourceResponse

from igs_common.db.base import uuid7
from igs_common.db.enums import ExecutionStatus, TriggerKind
from igs_common.db.models import Flow, FlowExecution, FlowNodeRun, FlowVersion
from igs_core.deps import AppSettings, CurrentPrincipal
from igs_core.errors import ProblemError
from igs_core.events import CHANNEL_NODE_RUNS, audit, emit
from igs_core.runtime import Hub, RequestId, Sessions, Workflows, Writer
from igs_core.schemas.common import Page, decode_cursor, encode_cursor, parse_cursor_value
from igs_core.schemas.workflows import (
    ExecutionDetail,
    ExecutionStartIn,
    ExecutionSummary,
    NodeRunOut,
)
from igs_core.schemas.workflows import (
    ExecutionStatus as ExecutionStatusName,
)
from igs_core.temporal import execution_input

router = APIRouter(tags=["executions"])
log = structlog.get_logger("igs_core.executions")

TERMINAL = {ExecutionStatus.SUCCEEDED, ExecutionStatus.FAILED, ExecutionStatus.CANCELLED}
POLL_SECONDS = 2.0


def manual_workflow_id(execution_id: UUID) -> str:
    return f"man-{execution_id}"


@router.post(
    "/flows/{flow_id}/executions",
    response_model=ExecutionSummary,
    status_code=202,
    summary="Start a manual / test run of a published version",
)
async def start_execution(
    flow_id: UUID,
    body: ExecutionStartIn,
    principal: Writer,
    sessions: Sessions,
    workflows: Workflows,
    rid: RequestId,
) -> ExecutionSummary:
    execution_id = uuid7()
    workflow_id = manual_workflow_id(execution_id)
    async with sessions(principal.tenant_id) as session:
        flow = await session.scalar(select(Flow).where(Flow.id == flow_id))
        if flow is None:
            raise ProblemError(404, "not-found", "Flow not found.")
        query = select(FlowVersion).where(FlowVersion.flow_id == flow_id)
        if body.version is not None:
            query = query.where(FlowVersion.version == body.version)
        elif flow.published_version_id is not None:
            query = query.where(FlowVersion.id == flow.published_version_id)
        else:
            raise ProblemError(409, "not-published", "Publish the flow before running it.")
        version = await session.scalar(query)
        if version is None:
            raise ProblemError(404, "not-found", "Version not found.")
        execution = FlowExecution(
            id=execution_id,
            tenant_id=principal.tenant_id,
            flow_version_id=version.id,
            trigger_kind=TriggerKind.MANUAL,
            trigger_payload=body.trigger,
            vars=body.vars,
            status=ExecutionStatus.RUNNING,
            temporal_workflow_id=workflow_id,
        )
        session.add(execution)
        await session.flush()
        await audit(
            session,
            principal,
            action="execution.started",
            subject_type="flow_execution",
            subject_id=execution_id,
            after={"flow": flow.key, "version": version.version},
            request_id=rid,
        )
        await emit(
            session,
            tenant_id=principal.tenant_id,
            type="execution.started",
            subject_type="flow_execution",
            subject_id=execution_id,
            payload={"flow": {"id": str(flow.id), "key": flow.key, "version": version.version}},
        )
        payload = execution_input(
            execution_id=str(execution_id),
            tenant_id=str(principal.tenant_id),
            graph=version.graph,
            version=version.version,
            trigger=body.trigger,
            vars=body.vars,
        )

    try:
        result = await workflows.start_execution(workflow_id, payload)
    except Exception as exc:  # noqa: BLE001 - surface as a failed run, not a phantom one
        log.warning("start_failed", workflow_id=workflow_id, exc_info=True)
        async with sessions(principal.tenant_id) as session:
            row = await session.get(FlowExecution, execution_id)
            if row is not None:
                row.status = ExecutionStatus.FAILED
                row.finished_at = datetime.now(UTC)
                row.error = {"class": "start", "message": f"{type(exc).__name__}: {exc}"}
        raise ProblemError(502, "workflows-unavailable", "Could not start the run.") from exc

    async with sessions(principal.tenant_id) as session:
        row = await session.get(FlowExecution, execution_id)
        assert row is not None
        if result.run_id:
            row.temporal_run_id = result.run_id
        await session.flush()
        return ExecutionSummary.model_validate(row)


@router.get(
    "/executions", response_model=Page[ExecutionSummary], summary="List executions (newest first)"
)
async def list_executions(
    principal: CurrentPrincipal,
    sessions: Sessions,
    settings: AppSettings,
    flow_id: UUID | None = None,
    status: ExecutionStatusName | None = None,
    subject_type: str | None = None,
    subject_id: UUID | None = None,
    cursor: str | None = None,
    limit: Annotated[int | None, Query(ge=1, le=200)] = None,
) -> Page[ExecutionSummary]:
    size = min(limit or settings.page_size_default, settings.page_size_max)
    query = select(FlowExecution).order_by(FlowExecution.started_at.desc(), FlowExecution.id.desc())
    if flow_id:
        query = query.join(FlowVersion, FlowVersion.id == FlowExecution.flow_version_id).where(
            FlowVersion.flow_id == flow_id
        )
    if status:
        query = query.where(FlowExecution.status == status)
    if subject_type:
        query = query.where(FlowExecution.subject_type == subject_type)
    if subject_id:
        query = query.where(FlowExecution.subject_id == subject_id)
    if cursor:
        at, eid = decode_cursor(cursor, 2)
        query = query.where(
            tuple_(FlowExecution.started_at, FlowExecution.id)
            < (parse_cursor_value(datetime.fromisoformat, at), parse_cursor_value(UUID, eid))
        )
    async with sessions(principal.tenant_id) as session:
        rows = (await session.scalars(query.limit(size + 1))).all()
        items = [ExecutionSummary.model_validate(r) for r in rows[:size]]
    more = len(rows) > size
    next_cursor = encode_cursor(items[-1].started_at.isoformat(), items[-1].id) if more else None
    return Page[ExecutionSummary](items=items, next_cursor=next_cursor)


async def _load_detail(session: Any, execution_id: UUID) -> ExecutionDetail:
    row = (
        await session.execute(
            select(FlowExecution, FlowVersion.version, Flow.id, Flow.key)
            .join(FlowVersion, FlowVersion.id == FlowExecution.flow_version_id)
            .join(Flow, Flow.id == FlowVersion.flow_id)
            .where(FlowExecution.id == execution_id)
        )
    ).first()
    if row is None:
        raise ProblemError(404, "not-found", "Execution not found.")
    execution, version, flow_id, flow_key = row
    runs = (
        await session.scalars(
            select(FlowNodeRun)
            .where(FlowNodeRun.execution_id == execution_id)
            .order_by(FlowNodeRun.started_at, FlowNodeRun.id)
        )
    ).all()
    return ExecutionDetail(
        **ExecutionSummary.model_validate(execution).model_dump(),
        flow_id=flow_id,
        flow_key=flow_key,
        version=version,
        trigger_payload=execution.trigger_payload,
        vars=execution.vars,
        error=execution.error,
        node_runs=[NodeRunOut.model_validate(r) for r in runs],
    )


@router.get(
    "/executions/{execution_id}",
    response_model=ExecutionDetail,
    summary="Execution with its node runs",
)
async def get_execution(
    execution_id: UUID, principal: CurrentPrincipal, sessions: Sessions
) -> ExecutionDetail:
    async with sessions(principal.tenant_id) as session:
        return await _load_detail(session, execution_id)


@router.post(
    "/executions/{execution_id}/cancel",
    response_model=ExecutionSummary,
    status_code=202,
    summary="Ask a running execution to stop",
)
async def cancel_execution(
    execution_id: UUID,
    principal: Writer,
    sessions: Sessions,
    workflows: Workflows,
    rid: RequestId,
) -> ExecutionSummary:
    async with sessions(principal.tenant_id) as session:
        row = await session.get(FlowExecution, execution_id)
        if row is None:
            raise ProblemError(404, "not-found", "Execution not found.")
        if row.status in TERMINAL:
            raise ProblemError(409, "already-finished", f"The execution is {row.status}.")
        workflow_id = row.temporal_workflow_id
        await audit(
            session,
            principal,
            action="execution.cancel_requested",
            subject_type="flow_execution",
            subject_id=execution_id,
            request_id=rid,
        )
        out = ExecutionSummary.model_validate(row)
    try:
        await workflows.cancel(workflow_id)
    except Exception as exc:  # noqa: BLE001
        raise ProblemError(502, "workflows-unavailable", "Could not reach the run.") from exc
    return out


@router.get(
    "/executions/{execution_id}/stream",
    summary="Live node-run updates (Server-Sent Events)",
    response_class=EventSourceResponse,
)
async def stream_execution(
    execution_id: UUID,
    request: Request,
    principal: CurrentPrincipal,
    sessions: Sessions,
    hub: Hub,
) -> EventSourceResponse:
    async with sessions(principal.tenant_id) as session:
        snapshot = await _load_detail(session, execution_id)

    async def events() -> AsyncIterator[dict[str, str]]:
        yield {"event": "snapshot", "data": snapshot.model_dump_json()}
        seen: dict[UUID, str] = {r.id: _fingerprint(r) for r in snapshot.node_runs}
        terminal = snapshot.status in {s.value for s in TERMINAL}
        while not terminal and not await request.is_disconnected():
            if hub is not None:
                await hub.wait(CHANNEL_NODE_RUNS, str(execution_id), wait_seconds=POLL_SECONDS)
            else:
                await asyncio.sleep(POLL_SECONDS)
            async with sessions(principal.tenant_id) as session:
                current = await _load_detail(session, execution_id)
            for run in current.node_runs:
                fp = _fingerprint(run)
                if seen.get(run.id) != fp:
                    seen[run.id] = fp
                    yield {"event": "node_run", "data": run.model_dump_json()}
            terminal = current.status in {s.value for s in TERMINAL}
            if terminal:
                yield {
                    "event": "end",
                    "data": json.dumps({"status": current.status, "error": current.error}),
                }

    # no-transform: proxies (Next rewrites) must not compress/buffer the event stream.
    return EventSourceResponse(
        events(), ping=15, headers={"Cache-Control": "no-cache, no-transform"}
    )


def _fingerprint(run: NodeRunOut) -> str:
    return f"{run.status}|{run.attempt}|{run.finished_at}"
