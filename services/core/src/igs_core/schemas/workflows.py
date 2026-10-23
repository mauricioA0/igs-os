"""Schemas for approvals, flows, executions and events."""

from datetime import datetime
from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel, Field

from igs_core.schemas.common import Schema

ApprovalStatus = Literal["pending", "approved", "rejected", "expired", "superseded"]
RiskClass = Literal["read", "internal_write", "external"]
ExecutionStatus = Literal["running", "waiting", "succeeded", "failed", "cancelled"]


class ProposedAction(BaseModel):
    action: str = Field(min_length=1, max_length=100)
    params: dict[str, Any] = Field(default_factory=dict)


class ApprovalSummary(Schema):
    id: UUID
    title: str
    status: ApprovalStatus
    risk_class: RiskClass
    assignee_role: str
    execution_id: UUID | None
    node_id: str | None
    created_at: datetime
    expires_at: datetime | None
    decided_at: datetime | None


class ApprovalDetail(ApprovalSummary):
    details: dict[str, Any]
    proposed_action: ProposedAction
    payload_hash: str
    comment: str | None
    superseded_by: UUID | None


class ApprovalCounts(BaseModel):
    """Counts by effective status: a pending approval past ``expires_at`` counts as expired."""

    pending: int
    expired: int
    approved: int
    rejected: int
    superseded: int


class ApprovalDecisionIn(BaseModel):
    decision: Literal["approved", "rejected"]
    payload_hash: str = Field(
        description="The hash shown to the approver. A mismatch means the action changed."
    )
    comment: str | None = Field(default=None, max_length=4000)
    edited_action: ProposedAction | None = Field(
        default=None,
        description="Edit-and-approve: a new approval with this action replaces the current one.",
    )


class ApprovalDecisionOut(BaseModel):
    approval: ApprovalDetail
    superseded: UUID | None = None
    signal_delivered: bool | None = Field(
        default=None, description="Null when the approval is not attached to a flow execution."
    )


class FlowSummary(Schema):
    id: UUID
    key: str
    name: str
    description: str
    draft_revision: int
    published_version: int | None
    updated_at: datetime
    archived_at: datetime | None


class FlowDetail(FlowSummary):
    draft_graph: dict[str, Any]


class FlowCreateIn(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    description: str = ""
    graph: dict[str, Any]


class FlowDraftIn(BaseModel):
    graph: dict[str, Any]
    name: str | None = Field(default=None, min_length=1, max_length=200)
    description: str | None = None


class ValidationProblem(BaseModel):
    code: str
    message: str
    severity: Literal["error", "warning"]
    node_id: str | None = None
    path: str | None = None


class ValidationOut(BaseModel):
    ok: bool
    problems: list[ValidationProblem]


class FlowVersionOut(Schema):
    id: UUID
    flow_id: UUID
    version: int
    graph_hash: str
    schema_version: str
    published_at: datetime
    changelog: str
    graph: dict[str, Any] | None = None


class PublishIn(BaseModel):
    changelog: str = Field(default="", max_length=4000)


class ExecutionStartIn(BaseModel):
    version: int | None = Field(default=None, description="Defaults to the published version.")
    trigger: dict[str, Any] = Field(default_factory=dict)
    vars: dict[str, Any] = Field(default_factory=dict)


class ExecutionSummary(Schema):
    id: UUID
    flow_version_id: UUID
    trigger_kind: str
    status: ExecutionStatus
    temporal_workflow_id: str
    started_at: datetime
    finished_at: datetime | None
    subject_type: str | None
    subject_id: UUID | None


class NodeRunOut(Schema):
    id: UUID
    node_id: str
    node_type: str
    attempt: int
    status: str
    input: Any | None
    output: Any | None
    error: dict[str, Any] | None
    started_at: datetime
    finished_at: datetime | None
    duration_ms: int | None


class ExecutionDetail(ExecutionSummary):
    flow_id: UUID
    flow_key: str
    version: int
    trigger_payload: dict[str, Any]
    vars: dict[str, Any]
    error: dict[str, Any] | None
    node_runs: list[NodeRunOut]


class EventIn(BaseModel):
    type: str = Field(pattern=r"^[a-z][a-z_]*\.[a-z_]+$", max_length=100)
    subject_type: str = Field(min_length=1, max_length=40)
    subject_id: UUID
    payload: dict[str, Any] = Field(default_factory=dict)


class EventOut(Schema):
    id: UUID
    type: str
    subject_type: str
    subject_id: UUID
    payload: dict[str, Any]
    occurred_at: datetime
    dispatched_at: datetime | None
    attempts: int
    last_error: str | None
