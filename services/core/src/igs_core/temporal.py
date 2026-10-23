"""The API's only seam to Temporal: start flow executions and send them signals.

Workflow ids are deterministic so retries are idempotent:

- ``evt-{event_id}-{flow_version_id}`` for event-triggered runs (outbox dispatcher),
- ``man-{execution_id}`` for manual and test runs started from the API.

The input shape mirrors ``igs_worker.workflows.flow_execution.ExecutionInput`` (dataclasses
through Temporal's JSON converter). ``execution_input`` is the one place that builds it.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any, Literal, Protocol

import structlog

from igs_common.temporal import connect_client, make_data_converter

if TYPE_CHECKING:
    from temporalio.client import Client
    from temporalio.converter import DataConverter

    from igs_core.config import Settings

WORKFLOW_TYPE = "FlowExecution"
SIGNAL_APPROVAL = "approval_decision"
SIGNAL_CANCEL = "cancel"

log = structlog.get_logger("igs_core.temporal")


def data_converter(settings: Settings) -> DataConverter:
    """Same converter as the worker: with a codec key set, payloads are encrypted both ways."""
    key = settings.temporal_codec_key.get_secret_value() if settings.temporal_codec_key else ""
    return make_data_converter(
        key, codec_key_id=settings.temporal_codec_key_id, environment=settings.environment
    )


def execution_input(
    *,
    execution_id: str,
    tenant_id: str,
    graph: dict[str, Any],
    version: int,
    trigger: dict[str, Any] | None = None,
    vars: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Workflow input for a pinned published version (never loaded inside the workflow)."""
    return {
        "execution_id": execution_id,
        # Domain actions run in the tenant's RLS scope; the worker never infers it.
        "tenant_id": tenant_id,
        "flow": {
            "flow_id": graph["id"],
            "version": version,
            "entry": graph["entry"],
            "nodes": [
                {
                    "id": n["id"],
                    "type": n["type"],
                    "config": n.get("config", {}),
                    "name": n.get("name"),
                    "disabled": n.get("disabled", False),
                    "on_error": n.get("onError", "fail"),
                    "retry": n.get("retry"),
                    "timeout": n.get("timeout"),
                }
                for n in graph["nodes"]
            ],
            "edges": [
                {"source": e["from"], "target": e["to"], "port": e.get("port", "next")}
                for e in graph["edges"]
            ],
            "settings": graph.get("settings", {}),
        },
        "trigger": trigger or {},
        "vars": vars or {},
    }


@dataclass(frozen=True)
class StartResult:
    workflow_id: str
    run_id: str | None
    already_started: bool = False


class WorkflowGateway(Protocol):
    async def start_execution(self, workflow_id: str, payload: dict[str, Any]) -> StartResult: ...

    async def signal_approval(
        self,
        workflow_id: str,
        *,
        node_id: str,
        decision: Literal["approved", "rejected"],
        by: str,
        comment: str = "",
        form: dict[str, Any] | None = None,
    ) -> None: ...

    async def cancel(self, workflow_id: str) -> None: ...


class TemporalGateway:
    """Lazily connected Temporal client. Safe to construct without a running server."""

    def __init__(self, settings: Settings) -> None:
        self._settings = settings
        self._client: Client | None = None
        self._lock = asyncio.Lock()

    async def _get(self) -> Client:
        if self._client is None:
            async with self._lock:
                if self._client is None:
                    self._client = await connect_client(
                        self._settings.temporal_address,
                        namespace=self._settings.temporal_namespace,
                        data_converter=data_converter(self._settings),
                    )
        return self._client

    async def start_execution(self, workflow_id: str, payload: dict[str, Any]) -> StartResult:
        from temporalio.exceptions import WorkflowAlreadyStartedError

        client = await self._get()
        try:
            handle = await client.start_workflow(
                WORKFLOW_TYPE,
                payload,
                id=workflow_id,
                task_queue=self._settings.temporal_task_queue_flows,
            )
        except WorkflowAlreadyStartedError:
            return StartResult(workflow_id, None, already_started=True)
        return StartResult(workflow_id, handle.result_run_id)

    async def signal_approval(
        self,
        workflow_id: str,
        *,
        node_id: str,
        decision: Literal["approved", "rejected"],
        by: str,
        comment: str = "",
        form: dict[str, Any] | None = None,
    ) -> None:
        client = await self._get()
        await client.get_workflow_handle(workflow_id).signal(
            SIGNAL_APPROVAL,
            {
                "node_id": node_id,
                "decision": decision,
                "by": by,
                "comment": comment,
                "form": form or {},
            },
        )

    async def cancel(self, workflow_id: str) -> None:
        client = await self._get()
        await client.get_workflow_handle(workflow_id).signal(SIGNAL_CANCEL)


@dataclass
class RecordingGateway:
    """In-memory gateway for tests and for running the API without Temporal."""

    started: dict[str, dict[str, Any]] = field(default_factory=dict)
    signals: list[tuple[str, str, dict[str, Any]]] = field(default_factory=list)
    fail: bool = False

    async def start_execution(self, workflow_id: str, payload: dict[str, Any]) -> StartResult:
        if self.fail:
            raise ConnectionError("temporal unavailable")
        if workflow_id in self.started:
            return StartResult(workflow_id, None, already_started=True)
        self.started[workflow_id] = payload
        return StartResult(workflow_id, f"run-{len(self.started)}")

    async def signal_approval(
        self,
        workflow_id: str,
        *,
        node_id: str,
        decision: Literal["approved", "rejected"],
        by: str,
        comment: str = "",
        form: dict[str, Any] | None = None,
    ) -> None:
        if self.fail:
            raise ConnectionError("temporal unavailable")
        self.signals.append(
            (
                workflow_id,
                SIGNAL_APPROVAL,
                {
                    "node_id": node_id,
                    "decision": decision,
                    "by": by,
                    "comment": comment,
                    "form": form or {},
                },
            )
        )

    async def cancel(self, workflow_id: str) -> None:
        if self.fail:
            raise ConnectionError("temporal unavailable")
        self.signals.append((workflow_id, SIGNAL_CANCEL, {}))
