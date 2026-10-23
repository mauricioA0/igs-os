import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import (
    BigInteger,
    Boolean,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from igs_common.db.base import Base, IdMixin, TenantMixin, TimestampMixin
from igs_common.db.enums import (
    ApprovalStatus,
    ExecutionStatus,
    NodeRunStatus,
    ToolClass,
    TriggerKind,
    UserRole,
    pg_enum,
)


class Flow(IdMixin, TimestampMixin, TenantMixin, Base):
    """The editable draft. Published snapshots live in flow_versions."""

    __tablename__ = "flows"
    __table_args__ = (Index("uq_flows_tenant_key", "tenant_id", "key", unique=True),)

    key: Mapped[str] = mapped_column(String(100))
    name: Mapped[str] = mapped_column(Text)
    description: Mapped[str] = mapped_column(Text, server_default="")
    draft_graph: Mapped[dict[str, Any]] = mapped_column(JSONB)
    # Optimistic concurrency for the editor (If-Match on save).
    draft_revision: Mapped[int] = mapped_column(Integer, server_default="1")
    draft_updated_by: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL")
    )
    # use_alter: flow_versions references flows too (cycle).
    published_version_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("flow_versions.id", ondelete="SET NULL", use_alter=True),
    )
    archived_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class FlowVersion(IdMixin, TimestampMixin, TenantMixin, Base):
    """Immutable published graph. Executions pin one."""

    __tablename__ = "flow_versions"
    __table_args__ = (UniqueConstraint("flow_id", "version"),)

    flow_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("flows.id", ondelete="CASCADE")
    )
    version: Mapped[int] = mapped_column(Integer)
    graph: Mapped[dict[str, Any]] = mapped_column(JSONB)
    graph_hash: Mapped[str] = mapped_column(String(64))
    schema_version: Mapped[str] = mapped_column(String(20))
    published_by: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL")
    )
    published_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=text("now()")
    )
    changelog: Mapped[str] = mapped_column(Text, server_default="")


class FlowTrigger(IdMixin, TimestampMixin, TenantMixin, Base):
    """Derived from the published graph on publish; indexed for event matching."""

    __tablename__ = "flow_triggers"
    __table_args__ = (
        Index("ix_flow_triggers_tenant_kind_enabled", "tenant_id", "kind", "enabled"),
        Index("ix_flow_triggers_config", "config", postgresql_using="gin"),
    )

    flow_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("flows.id", ondelete="CASCADE")
    )
    kind: Mapped[TriggerKind] = mapped_column(pg_enum(TriggerKind, "trigger_kind"))
    config: Mapped[dict[str, Any]] = mapped_column(JSONB, server_default="{}")
    enabled: Mapped[bool] = mapped_column(Boolean, server_default=text("true"))


class FlowExecution(IdMixin, TimestampMixin, TenantMixin, Base):
    """Queryable projection of a Temporal workflow run."""

    __tablename__ = "flow_executions"
    __table_args__ = (
        Index(
            "ix_flow_executions_tenant_version_started",
            "tenant_id",
            "flow_version_id",
            text("started_at DESC"),
        ),
        Index("ix_flow_executions_tenant_status", "tenant_id", "status"),
        Index("ix_flow_executions_subject", "subject_type", "subject_id"),
    )

    flow_version_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("flow_versions.id", ondelete="RESTRICT")
    )
    trigger_kind: Mapped[TriggerKind] = mapped_column(pg_enum(TriggerKind, "trigger_kind"))
    trigger_payload: Mapped[dict[str, Any]] = mapped_column(JSONB, server_default="{}")
    status: Mapped[ExecutionStatus] = mapped_column(
        pg_enum(ExecutionStatus, "execution_status"), server_default=ExecutionStatus.RUNNING.value
    )
    temporal_workflow_id: Mapped[str] = mapped_column(Text, unique=True)
    temporal_run_id: Mapped[str | None] = mapped_column(Text)
    vars: Mapped[dict[str, Any]] = mapped_column(JSONB, server_default="{}")
    error: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    started_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=text("now()")
    )
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    parent_execution_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("flow_executions.id", ondelete="SET NULL")
    )
    subject_type: Mapped[str | None] = mapped_column(String(40))
    subject_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))


class FlowNodeRun(IdMixin, TimestampMixin, TenantMixin, Base):
    """One attempt of one node. Outputs >256 KB are stored in GCS and referenced here."""

    __tablename__ = "flow_node_runs"
    __table_args__ = (Index("ix_flow_node_runs_execution_started", "execution_id", "started_at"),)

    execution_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("flow_executions.id", ondelete="CASCADE")
    )
    node_id: Mapped[str] = mapped_column(String(100))
    node_type: Mapped[str] = mapped_column(String(60))
    attempt: Mapped[int] = mapped_column(Integer, server_default="1")
    status: Mapped[NodeRunStatus] = mapped_column(pg_enum(NodeRunStatus, "node_run_status"))
    input: Mapped[Any | None] = mapped_column(JSONB)
    output: Mapped[Any | None] = mapped_column(JSONB)
    error: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    started_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=text("now()")
    )
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    duration_ms: Mapped[int | None] = mapped_column(BigInteger)  # waits can last months
    idempotency_key: Mapped[str] = mapped_column(Text, unique=True)


class Approval(IdMixin, TimestampMixin, TenantMixin, Base):
    """A human decision bound to an exact action: any payload change needs a new approval."""

    __tablename__ = "approvals"
    __table_args__ = (
        Index(
            "ix_approvals_inbox",
            "tenant_id",
            "assignee_role",
            postgresql_where="status = 'pending'",
        ),
        Index("ix_approvals_execution", "execution_id"),
        Index("ix_approvals_subject", "tenant_id", "subject_type", "subject_id"),
    )

    # Null when the approval comes from the copilot/MCP rather than a flow node.
    execution_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("flow_executions.id", ondelete="CASCADE")
    )
    node_id: Mapped[str | None] = mapped_column(String(100))
    # What the approval is about, for "approvals of this trip/lead/account" views.
    subject_type: Mapped[str | None] = mapped_column(String(40))  # trip | lead | account | …
    subject_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    title: Mapped[str] = mapped_column(Text)
    details: Mapped[dict[str, Any]] = mapped_column(JSONB, server_default="{}")
    # {"action": "send_email", "params": {...}} in canonical form; hashed into payload_hash.
    proposed_action: Mapped[dict[str, Any]] = mapped_column(JSONB)
    payload_hash: Mapped[str] = mapped_column(String(80))  # "sha256:<hex>", algorithm-prefixed
    risk_class: Mapped[ToolClass] = mapped_column(pg_enum(ToolClass, "tool_class"))
    assignee_role: Mapped[UserRole] = mapped_column(pg_enum(UserRole, "user_role"))
    assignee_user_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL")
    )
    status: Mapped[ApprovalStatus] = mapped_column(
        pg_enum(ApprovalStatus, "approval_status"), server_default=ApprovalStatus.PENDING.value
    )
    decided_by: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL")
    )
    decided_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    comment: Mapped[str | None] = mapped_column(Text)
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    # "Edit and approve" creates a new approval and points the old one at it.
    superseded_by: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("approvals.id", ondelete="SET NULL")
    )
