"""Outbox dispatcher: turns committed domain events into flow executions.

Loop: claim pending events with ``FOR UPDATE SKIP LOCKED`` (several dispatchers can run side
by side), find published flows whose trigger is ``{"type": "event", "event": <type>}`` and whose
optional CEL ``filter`` matches, record the execution and start it in Temporal with the
workflow id ``evt-{event_id}-{flow_version_id}``. A redelivered event maps to the same id, so it
never starts a flow twice. Between batches it sleeps until a NOTIFY on ``igs_outbox`` or a poll
interval, whichever comes first.

Run standalone: ``python -m igs_core.events.dispatcher``.
"""

import asyncio
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any
from uuid import UUID

import structlog
from sqlalchemy import select, update
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession

from igs_common.db import session as shared
from igs_common.db.enums import ExecutionStatus, TriggerKind
from igs_common.db.models import Flow, FlowExecution, FlowVersion, OutboxEvent
from igs_common.flows.cel import evaluate_bool
from igs_core.events.listen import NotificationHub
from igs_core.events.outbox import CHANNEL_OUTBOX
from igs_core.temporal import WorkflowGateway, execution_input

log = structlog.get_logger("igs_core.events.dispatcher")

MAX_ATTEMPTS = 10


def event_workflow_id(event_id: UUID, flow_version_id: UUID) -> str:
    return f"evt-{event_id}-{flow_version_id}"


def trigger_matches(graph: dict[str, Any], event: OutboxEvent) -> bool:
    """True when the flow's event trigger names this event and its filter (if any) passes."""
    trigger = graph.get("trigger") or {}
    if trigger.get("type") != "event" or trigger.get("event") != event.type:
        return False
    source = trigger.get("filter")
    if not source:
        return True
    try:
        return evaluate_bool(source, {"trigger": event.payload})
    except Exception:  # noqa: BLE001 - a broken filter must not block the outbox
        log.warning("trigger_filter_failed", event_id=str(event.id), exc_info=True)
        return False


@dataclass
class DispatchStats:
    events: int = 0
    executions: int = 0
    failures: int = 0


class OutboxDispatcher:
    def __init__(
        self,
        gateway: WorkflowGateway,
        *,
        engine: AsyncEngine | None = None,
        batch_size: int = 50,
        poll_interval: float = 5.0,
    ) -> None:
        self._gateway = gateway
        self._engine = engine
        self._batch = batch_size
        self._poll = poll_interval
        self._stop = asyncio.Event()

    async def run_once(self) -> DispatchStats:
        stats = DispatchStats()
        async with shared.system_scope(engine=self._engine) as session:
            events = (
                await session.scalars(
                    select(OutboxEvent)
                    .where(
                        OutboxEvent.dispatched_at.is_(None),
                        OutboxEvent.attempts < MAX_ATTEMPTS,
                    )
                    .order_by(OutboxEvent.occurred_at, OutboxEvent.id)
                    .limit(self._batch)
                    .with_for_update(skip_locked=True)
                )
            ).all()
            for event in events:
                stats.events += 1
                try:
                    stats.executions += await self._dispatch(session, event)
                    event.dispatched_at = datetime.now(UTC)
                    event.last_error = None
                except Exception as exc:  # noqa: BLE001 - retried on the next pass
                    stats.failures += 1
                    event.attempts += 1
                    event.last_error = f"{type(exc).__name__}: {exc}"[:2000]
                    log.warning("dispatch_failed", event_id=str(event.id), exc_info=True)
        return stats

    async def _dispatch(self, session: AsyncSession, event: OutboxEvent) -> int:
        rows = (
            await session.execute(
                select(FlowVersion.id, FlowVersion.version, FlowVersion.graph)
                .join(Flow, Flow.published_version_id == FlowVersion.id)
                .where(
                    Flow.tenant_id == event.tenant_id,
                    Flow.archived_at.is_(None),
                    FlowVersion.graph["trigger"]["type"].astext == "event",
                    FlowVersion.graph["trigger"]["event"].astext == event.type,
                )
            )
        ).all()
        started = 0
        for version_id, version, graph in rows:
            if not trigger_matches(graph, event):
                continue
            workflow_id = event_workflow_id(event.id, version_id)
            execution_id = await session.scalar(
                insert(FlowExecution)
                .values(
                    tenant_id=event.tenant_id,
                    flow_version_id=version_id,
                    trigger_kind=TriggerKind.EVENT,
                    trigger_payload={"event": event.type, **event.payload},
                    status=ExecutionStatus.RUNNING,
                    temporal_workflow_id=workflow_id,
                    subject_type=event.subject_type,
                    subject_id=event.subject_id,
                )
                .on_conflict_do_nothing(index_elements=["temporal_workflow_id"])
                .returning(FlowExecution.id)
            )
            if execution_id is None:  # redelivery: reuse the execution already recorded
                execution_id = await session.scalar(
                    select(FlowExecution.id).where(
                        FlowExecution.temporal_workflow_id == workflow_id
                    )
                )
            payload = execution_input(
                execution_id=str(execution_id),
                tenant_id=str(event.tenant_id),
                graph=graph,
                version=version,
                trigger={"event": event.type, **event.payload},
            )
            result = await self._gateway.start_execution(workflow_id, payload)
            if result.run_id:
                await session.execute(
                    update(FlowExecution)
                    .where(FlowExecution.id == execution_id)
                    .values(temporal_run_id=result.run_id)
                )
            started += 1
        return started

    def stop(self) -> None:
        self._stop.set()

    async def run_forever(self, hub: NotificationHub | None = None) -> None:
        log.info("dispatcher_started")
        while not self._stop.is_set():
            try:
                stats = await self.run_once()
            except Exception:  # noqa: BLE001 - keep the loop alive (db blips)
                log.exception("dispatcher_pass_failed")
                stats = DispatchStats()
            if stats.events:
                log.info("dispatched", **stats.__dict__)
                continue  # drain the backlog before sleeping
            if hub is not None:
                await hub.wait(CHANNEL_OUTBOX, wait_seconds=self._poll)
            else:
                try:
                    await asyncio.wait_for(self._stop.wait(), self._poll)
                except TimeoutError:
                    pass
        log.info("dispatcher_stopped")


async def main() -> None:
    from igs_core.config import get_settings
    from igs_core.logs import configure_logging
    from igs_core.temporal import TemporalGateway

    settings = get_settings()
    configure_logging(settings.log_level, json=settings.log_json)
    engine = shared.configure(settings.database_url)
    hub = NotificationHub(engine, (CHANNEL_OUTBOX,))
    dispatcher = OutboxDispatcher(TemporalGateway(settings), engine=engine)
    try:
        await dispatcher.run_forever(hub)
    finally:
        await hub.stop()
        await shared.dispose()


if __name__ == "__main__":
    asyncio.run(main())
