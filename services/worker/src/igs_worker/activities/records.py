"""Bookkeeping activities: node-run records, approvals, published versions for subflows."""

from dataclasses import dataclass, field
from typing import Any, Protocol

from temporalio import activity
from temporalio.exceptions import ApplicationError

from ..flow_model import FlowVersion
from .types import ApprovalRequest, FlowVersionRef, NodeRunRecord


class NodeRunSink(Protocol):
    async def write(self, records: list[NodeRunRecord]) -> None: ...


class ApprovalStore(Protocol):
    async def create(self, req: ApprovalRequest) -> str: ...


class FlowVersionStore(Protocol):
    async def load(self, ref: FlowVersionRef) -> dict[str, Any]: ...


@dataclass
class InMemorySink:
    records: list[NodeRunRecord] = field(default_factory=list)

    async def write(self, records: list[NodeRunRecord]) -> None:
        self.records.extend(records)


@dataclass
class InMemoryApprovals:
    created: list[ApprovalRequest] = field(default_factory=list)

    async def create(self, req: ApprovalRequest) -> str:
        self.created.append(req)
        # Deterministic id: a retried activity must not create a second approval.
        suffix = f"-{req.seq}" if req.seq else ""
        return f"apr-{req.execution_id}-{req.node_id}-{req.iteration}{suffix}"


@dataclass
class InMemoryFlowVersions:
    """Published versions keyed by (flow_id, version).

    Phase 4 reads ``flow_versions`` in Postgres instead.
    """

    docs: dict[tuple[str, int], dict[str, Any]] = field(default_factory=dict)

    def publish(self, doc: dict[str, Any], version: int) -> None:
        self.docs[(doc["id"], version)] = {**doc, "version": version}

    async def load(self, ref: FlowVersionRef) -> dict[str, Any]:
        versions = sorted(v for (f, v) in self.docs if f == ref.flow_id)
        if not versions:
            raise ApplicationError(
                f"flow {ref.flow_id!r} has no published version",
                type="not_found",
                non_retryable=True,
            )
        v = ref.version if ref.version is not None else versions[-1]
        if (ref.flow_id, v) not in self.docs:
            raise ApplicationError(
                f"{ref.flow_id}@v{v} not found", type="not_found", non_retryable=True
            )
        return self.docs[(ref.flow_id, v)]


@dataclass
class RecordActivities:
    sink: NodeRunSink = field(default_factory=InMemorySink)
    approvals: ApprovalStore = field(default_factory=InMemoryApprovals)
    versions: FlowVersionStore = field(default_factory=InMemoryFlowVersions)

    @activity.defn(name="flow.record_node_runs")
    async def record_node_runs(self, records: list[NodeRunRecord]) -> None:
        # Idempotent upsert on (execution_id, node_id, iteration) in Postgres (phase 4).
        await self.sink.write(records)

    @activity.defn(name="flow.create_approval")
    async def create_approval(self, req: ApprovalRequest) -> str:
        return await self.approvals.create(req)

    @activity.defn(name="flow.load_version")
    async def load_version(self, ref: FlowVersionRef) -> FlowVersion:
        doc = await self.versions.load(ref)
        return FlowVersion.from_json(doc)

    def all(self) -> list[Any]:
        return [self.record_node_runs, self.create_approval, self.load_version]
