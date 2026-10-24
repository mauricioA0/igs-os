"""Agent traces, documents/ingestion, outbox and audit."""

import uuid
from datetime import date, datetime
from decimal import Decimal
from typing import Any

from pgvector.sqlalchemy import Vector
from sqlalchemy import (
    Boolean,
    CheckConstraint,
    Computed,
    Date,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    Text,
    text,
)
from sqlalchemy.dialects.postgresql import ARRAY, JSONB, TSVECTOR, UUID
from sqlalchemy.orm import Mapped, mapped_column

from igs_common.db.base import Base, IdMixin, TenantMixin, TimestampMixin
from igs_common.db.enums import (
    ActorType,
    AgentSurface,
    DocumentStatus,
    IngestionStatus,
    pg_enum,
)

# ── Agents and tracing ─────────────────────────────────────────────────────


class AgentRun(IdMixin, TimestampMixin, TenantMixin, Base):
    __tablename__ = "agent_runs"
    __table_args__ = (
        Index(
            "ix_agent_runs_tenant_surface_started", "tenant_id", "surface", text("started_at DESC")
        ),
        Index("ix_agent_runs_conversation", "conversation_id"),
    )

    conversation_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("conversations.id", ondelete="SET NULL")
    )
    # No FK: flow_node_runs is a high-volume table that gets partitioned later.
    flow_node_run_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    surface: Mapped[AgentSurface] = mapped_column(pg_enum(AgentSurface, "agent_surface"))
    model: Mapped[str] = mapped_column(Text)
    started_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=text("now()")
    )
    latency_ms: Mapped[int | None] = mapped_column(Integer)
    input_tokens: Mapped[int] = mapped_column(Integer, server_default="0")
    output_tokens: Mapped[int] = mapped_column(Integer, server_default="0")
    cache_read_tokens: Mapped[int] = mapped_column(Integer, server_default="0")
    cache_write_tokens: Mapped[int] = mapped_column(Integer, server_default="0")
    cost_usd: Mapped[Decimal] = mapped_column(Numeric(10, 6), server_default="0")
    stop_reason: Mapped[str | None] = mapped_column(Text)
    error: Mapped[str | None] = mapped_column(Text)
    trace_id: Mapped[str | None] = mapped_column(String(32))


class AgentStep(IdMixin, TimestampMixin, TenantMixin, Base):
    __tablename__ = "agent_steps"
    __table_args__ = (Index("ix_agent_steps_run_idx", "run_id", "idx"),)

    run_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("agent_runs.id", ondelete="CASCADE")
    )
    idx: Mapped[int] = mapped_column(Integer)
    tool: Mapped[str] = mapped_column(Text)
    input: Mapped[Any] = mapped_column(JSONB)
    output: Mapped[Any | None] = mapped_column(JSONB)
    is_error: Mapped[bool] = mapped_column(Boolean, server_default=text("false"))
    duration_ms: Mapped[int] = mapped_column(Integer)


EMBEDDING_DIMS = 1024

# ── Documents and ingestion ───────────────────────────────────────────────


class Document(IdMixin, TimestampMixin, TenantMixin, Base):
    __tablename__ = "documents"
    __table_args__ = (
        Index("uq_documents_tenant_content_hash", "tenant_id", "content_hash", unique=True),
        Index("ix_documents_tenant_status", "tenant_id", "status"),
    )

    title: Mapped[str] = mapped_column(Text)
    source: Mapped[str] = mapped_column(String(40))  # policy, contract, guide, trip_report, faq…
    # Where the source text lives: GCS for uploads, inline for small seeded/pasted docs.
    gcs_uri: Mapped[str | None] = mapped_column(Text)
    inline_content: Mapped[str | None] = mapped_column(Text)
    mime_type: Mapped[str] = mapped_column(String(100))
    content_hash: Mapped[str] = mapped_column(String(64))
    metadata_: Mapped[dict[str, Any]] = mapped_column("metadata", JSONB, server_default="{}")
    status: Mapped[DocumentStatus] = mapped_column(
        pg_enum(DocumentStatus, "document_status"), server_default=DocumentStatus.PENDING.value
    )
    current_job_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    chunk_count: Mapped[int] = mapped_column(Integer, server_default="0")
    embedding_model: Mapped[str | None] = mapped_column(Text)


class DocumentChunk(IdMixin, TimestampMixin, TenantMixin, Base):
    """A retrievable chunk of a document **or** of an Account 360 interaction (exactly one)."""

    __tablename__ = "document_chunks"
    __table_args__ = (
        CheckConstraint("(document_id IS NULL) <> (interaction_id IS NULL)", name="one_source"),
        Index("ix_document_chunks_document_ordinal", "document_id", "ordinal"),
        Index("uq_document_chunks_document_hash", "document_id", "content_hash", unique=True),
        Index("uq_document_chunks_interaction_hash", "interaction_id", "content_hash", unique=True),
        Index("ix_document_chunks_account", "tenant_id", "account_id"),
        Index(
            "ix_document_chunks_tenant_vobj",
            "tenant_id",
            "vector_object_id",
            postgresql_where="vector_object_id IS NOT NULL",
        ),
        Index(
            "ix_document_chunks_quarantined",
            "tenant_id",
            postgresql_where="quarantined",
        ),
        Index(
            "ix_document_chunks_embedding_hnsw",
            "embedding",
            postgresql_using="hnsw",
            postgresql_ops={"embedding": "vector_cosine_ops"},
        ),
        Index("ix_document_chunks_tsv", "tsv", postgresql_using="gin"),
        Index(
            "ix_document_chunks_payload",
            "payload",
            postgresql_using="gin",
            postgresql_ops={"payload": "jsonb_path_ops"},
        ),
    )

    document_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("documents.id", ondelete="CASCADE")
    )
    interaction_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("interactions.id", ondelete="CASCADE")
    )
    # Denormalized so the RAG can filter by client without a join.
    account_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("accounts.id", ondelete="CASCADE")
    )
    ordinal: Mapped[int] = mapped_column(Integer)
    content: Mapped[str] = mapped_column(Text)
    token_count: Mapped[int] = mapped_column(Integer)
    heading_path: Mapped[list[str]] = mapped_column(ARRAY(Text), server_default="{}")
    content_hash: Mapped[str] = mapped_column(String(64))
    vector_object_id: Mapped[str | None] = mapped_column(String(63))
    # pgvector store (default/local). BGE-M3 dense = 1024 dims; null until embedded.
    embedding: Mapped[list[float] | None] = mapped_column(Vector(EMBEDDING_DIMS))
    # BGE-M3 lexical weights: {"<token id>": weight}.
    sparse: Mapped[dict[str, float] | None] = mapped_column(JSONB)
    # Filter/store fields of the vector-store object (title, source, account, dates…).
    payload: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    # Keyword side of hybrid search, title included. 'simple' config: corpus mixes EN and ES.
    tsv: Mapped[str] = mapped_column(
        TSVECTOR,
        Computed(
            "to_tsvector('simple', coalesce(payload->>'title', '') || ' ' || content)",
            persisted=True,
        ),
    )
    # Ingestion hygiene: suspected prompt injection is kept out of retrieval until reviewed.
    quarantined: Mapped[bool] = mapped_column(Boolean, server_default=text("false"))
    quarantine_reason: Mapped[str | None] = mapped_column(Text)
    quarantined_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    reviewed_by: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL")
    )
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class IngestionJob(IdMixin, TimestampMixin, TenantMixin, Base):
    __tablename__ = "ingestion_jobs"
    __table_args__ = (Index("ix_ingestion_jobs_document", "document_id", "started_at"),)

    document_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("documents.id", ondelete="CASCADE")
    )
    temporal_workflow_id: Mapped[str | None] = mapped_column(Text)
    status: Mapped[IngestionStatus] = mapped_column(
        pg_enum(IngestionStatus, "ingestion_status"), server_default=IngestionStatus.QUEUED.value
    )
    embedding_model: Mapped[str | None] = mapped_column(Text)
    stats: Mapped[dict[str, Any]] = mapped_column(JSONB, server_default="{}")
    error: Mapped[str | None] = mapped_column(Text)
    started_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=text("now()")
    )
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class RetrievalEvalRun(IdMixin, TimestampMixin, TenantMixin, Base):
    __tablename__ = "retrieval_eval_runs"
    __table_args__ = (Index("ix_retrieval_eval_runs_tenant_created", "tenant_id", "created_at"),)

    embedding_model: Mapped[str] = mapped_column(Text)
    reranker: Mapped[str | None] = mapped_column(Text)
    dataset_version: Mapped[str] = mapped_column(Text)
    metrics: Mapped[dict[str, Any]] = mapped_column(JSONB)
    git_sha: Mapped[str | None] = mapped_column(String(40))


# ── Events and audit ──────────────────────────────────────────────────────


class OutboxEvent(IdMixin, TimestampMixin, TenantMixin, Base):
    """Written in the same transaction as the change; dispatched with FOR UPDATE SKIP LOCKED."""

    __tablename__ = "outbox_events"
    __table_args__ = (
        Index(
            "ix_outbox_events_pending",
            "occurred_at",
            postgresql_where="dispatched_at IS NULL",
        ),
    )

    type: Mapped[str] = mapped_column(String(100))
    subject_type: Mapped[str] = mapped_column(String(40))
    subject_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True))
    payload: Mapped[dict[str, Any]] = mapped_column(JSONB, server_default="{}")
    occurred_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=text("now()")
    )
    dispatched_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    attempts: Mapped[int] = mapped_column(Integer, server_default="0")
    last_error: Mapped[str | None] = mapped_column(Text)


class AuditLog(IdMixin, TimestampMixin, TenantMixin, Base):
    """Append-only: the app role gets INSERT/SELECT only (see migration grants)."""

    __tablename__ = "audit_log"
    __table_args__ = (
        Index(
            "ix_audit_log_subject",
            "tenant_id",
            "subject_type",
            "subject_id",
            text("at DESC"),
        ),
        Index("ix_audit_log_at_brin", "at", postgresql_using="brin"),
    )

    actor_type: Mapped[ActorType] = mapped_column(pg_enum(ActorType, "actor_type"))
    actor_id: Mapped[str | None] = mapped_column(Text)
    action: Mapped[str] = mapped_column(String(100))
    subject_type: Mapped[str] = mapped_column(String(40))
    subject_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    before: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    after: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    request_id: Mapped[str | None] = mapped_column(String(64))
    at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=text("now()"))


# ── Model spend ───────────────────────────────────────────────────────────


class LlmSpendDaily(Base):
    """Model spend per UTC day, across tenants: backs the deployment-wide daily cap.

    Not tenant-scoped on purpose: the cap protects the provider bill, which is one per
    deployment (igs_common.llm.budget).
    """

    __tablename__ = "llm_spend_daily"

    day: Mapped[date] = mapped_column(Date, primary_key=True)
    cost_usd: Mapped[Decimal] = mapped_column(Numeric(12, 6), server_default="0", nullable=False)
    calls: Mapped[int] = mapped_column(Integer, server_default="0", nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=text("now()"), nullable=False
    )
