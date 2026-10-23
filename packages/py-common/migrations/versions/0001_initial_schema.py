"""initial schema

Revision ID: 0001
Revises:
Create Date: 2026-10-22 21:59:33.186095+00:00
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0001"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


# Inlined (not imported from igs_common.db.rls) so this revision never changes behavior.
APP_ROLE = "igs_app"
TENANT_GUC = "app.tenant_id"
UNSCOPED_TABLES = ("tenants",)
APPEND_ONLY_TABLES = ("audit_log", "messages")

ENUMS: dict[str, tuple[str, ...]] = {
    "account_health": (
        "green",
        "amber",
        "red",
    ),
    "account_kind": (
        "university",
        "club",
        "high_school",
        "family_group",
    ),
    "account_status": (
        "prospect",
        "active",
        "past",
        "churned",
    ),
    "actor_type": (
        "user",
        "agent",
        "flow",
        "api_key",
        "system",
    ),
    "agent_surface": (
        "chat",
        "flow",
        "mcp",
        "copilot",
        "eval",
    ),
    "approval_status": (
        "pending",
        "approved",
        "rejected",
        "expired",
        "superseded",
    ),
    "channel": (
        "web",
        "whatsapp",
        "email",
        "mcp",
    ),
    "direction": (
        "inbound",
        "outbound",
        "internal",
    ),
    "document_status": (
        "pending",
        "ingesting",
        "ready",
        "failed",
    ),
    "execution_status": (
        "running",
        "waiting",
        "succeeded",
        "failed",
        "cancelled",
    ),
    "fact_kind": (
        "status",
        "commitment",
        "risk",
        "preference",
        "budget",
        "decision",
    ),
    "gender": (
        "men",
        "women",
        "mixed",
    ),
    "incident_severity": (
        "low",
        "medium",
        "high",
        "critical",
    ),
    "incident_status": (
        "open",
        "mitigating",
        "resolved",
    ),
    "ingestion_status": (
        "queued",
        "parsing",
        "chunking",
        "embedding",
        "indexing",
        "succeeded",
        "failed",
    ),
    "interaction_channel": (
        "email",
        "call",
        "meeting",
        "chat",
        "whatsapp",
        "note",
    ),
    "item_kind": (
        "arrival",
        "departure",
        "match",
        "training",
        "experience",
        "free",
    ),
    "item_slot": (
        "morning",
        "afternoon",
        "evening",
    ),
    "item_status": (
        "pending",
        "requested",
        "confirmed",
        "completed",
        "cancelled",
    ),
    "lead_source": (
        "chat",
        "webhook",
        "manual",
        "flow",
    ),
    "lead_status": (
        "new",
        "qualified",
        "proposal_sent",
        "won",
        "lost",
    ),
    "message_role": (
        "user",
        "assistant",
    ),
    "node_run_status": (
        "running",
        "succeeded",
        "failed",
        "skipped",
        "waiting",
    ),
    "provider_kind": (
        "hotel",
        "transport",
        "venue",
        "referee",
        "guide",
        "club",
    ),
    "sentiment": (
        "positive",
        "neutral",
        "negative",
        "unknown",
    ),
    "sport": (
        "soccer",
        "rugby",
        "field_hockey",
        "volleyball",
        "basketball",
    ),
    "stakeholder_role": (
        "decision_maker",
        "champion",
        "coach",
        "assistant_coach",
        "athletic_director",
        "compliance",
        "travel_coordinator",
        "finance",
        "parent_liaison",
        "other",
    ),
    "tool_class": (
        "read",
        "internal_write",
        "external",
    ),
    "trigger_kind": (
        "chat",
        "webhook",
        "schedule",
        "event",
        "manual",
    ),
    "trip_status": (
        "draft",
        "proposed",
        "confirmed",
        "in_progress",
        "completed",
        "cancelled",
    ),
    "user_role": (
        "owner",
        "ops",
        "sales",
        "viewer",
    ),
}

# Tenant-scoped tables: RLS + app-role grants.
TENANT_TABLES: tuple[str, ...] = (
    "audit_log",
    "documents",
    "outbox_events",
    "providers",
    "retrieval_eval_runs",
    "users",
    "accounts",
    "api_keys",
    "experiences",
    "flows",
    "ingestion_jobs",
    "opponents",
    "contacts",
    "flow_triggers",
    "flow_versions",
    "flow_executions",
    "stakeholders",
    "approvals",
    "conversations",
    "flow_node_runs",
    "agent_runs",
    "leads",
    "messages",
    "agent_steps",
    "trips",
    "interactions",
    "trip_items",
    "account_facts",
    "document_chunks",
    "incidents",
)


def upgrade() -> None:
    _create_app_role()
    for name, values in ENUMS.items():
        postgresql.ENUM(*values, name=name).create(op.get_bind(), checkfirst=True)

    # ### commands auto generated by Alembic - please adjust! ###
    op.create_table(
        "tenants",
        sa.Column("slug", sa.String(length=63), nullable=False),
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column(
            "settings", postgresql.JSONB(astext_type=sa.Text()), server_default="{}", nullable=False
        ),
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_tenants")),
        sa.UniqueConstraint("slug", name=op.f("uq_tenants_slug")),
    )
    op.create_table(
        "audit_log",
        sa.Column(
            "actor_type",
            postgresql.ENUM(
                "user", "agent", "flow", "api_key", "system", name="actor_type", create_type=False
            ),
            nullable=False,
        ),
        sa.Column("actor_id", sa.Text(), nullable=True),
        sa.Column("action", sa.String(length=100), nullable=False),
        sa.Column("subject_type", sa.String(length=40), nullable=False),
        sa.Column("subject_id", sa.UUID(), nullable=True),
        sa.Column("before", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("after", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("request_id", sa.String(length=64), nullable=True),
        sa.Column(
            "at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False
        ),
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("tenant_id", sa.UUID(), nullable=False),
        sa.ForeignKeyConstraint(
            ["tenant_id"],
            ["tenants.id"],
            name=op.f("fk_audit_log_tenant_id_tenants"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_audit_log")),
    )
    op.create_index(
        "ix_audit_log_at_brin", "audit_log", ["at"], unique=False, postgresql_using="brin"
    )
    op.create_index(
        "ix_audit_log_subject",
        "audit_log",
        ["tenant_id", "subject_type", "subject_id", sa.literal_column("at DESC")],
        unique=False,
    )
    op.create_table(
        "documents",
        sa.Column("title", sa.Text(), nullable=False),
        sa.Column("source", sa.String(length=40), nullable=False),
        sa.Column("gcs_uri", sa.Text(), nullable=True),
        sa.Column("mime_type", sa.String(length=100), nullable=False),
        sa.Column("content_hash", sa.String(length=64), nullable=False),
        sa.Column(
            "metadata", postgresql.JSONB(astext_type=sa.Text()), server_default="{}", nullable=False
        ),
        sa.Column(
            "status",
            postgresql.ENUM(
                "pending", "ingesting", "ready", "failed", name="document_status", create_type=False
            ),
            server_default="pending",
            nullable=False,
        ),
        sa.Column("current_job_id", sa.UUID(), nullable=True),
        sa.Column("chunk_count", sa.Integer(), server_default="0", nullable=False),
        sa.Column("embedding_model", sa.Text(), nullable=True),
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("tenant_id", sa.UUID(), nullable=False),
        sa.ForeignKeyConstraint(
            ["tenant_id"],
            ["tenants.id"],
            name=op.f("fk_documents_tenant_id_tenants"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_documents")),
    )
    op.create_index(
        "ix_documents_tenant_status", "documents", ["tenant_id", "status"], unique=False
    )
    op.create_index(
        "uq_documents_tenant_content_hash", "documents", ["tenant_id", "content_hash"], unique=True
    )
    op.create_table(
        "outbox_events",
        sa.Column("type", sa.String(length=100), nullable=False),
        sa.Column("subject_type", sa.String(length=40), nullable=False),
        sa.Column("subject_id", sa.UUID(), nullable=False),
        sa.Column(
            "payload", postgresql.JSONB(astext_type=sa.Text()), server_default="{}", nullable=False
        ),
        sa.Column(
            "occurred_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("dispatched_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("attempts", sa.Integer(), server_default="0", nullable=False),
        sa.Column("last_error", sa.Text(), nullable=True),
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("tenant_id", sa.UUID(), nullable=False),
        sa.ForeignKeyConstraint(
            ["tenant_id"],
            ["tenants.id"],
            name=op.f("fk_outbox_events_tenant_id_tenants"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_outbox_events")),
    )
    op.create_index(
        "ix_outbox_events_pending",
        "outbox_events",
        ["occurred_at"],
        unique=False,
        postgresql_where="dispatched_at IS NULL",
    )
    op.create_table(
        "providers",
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column(
            "kind",
            postgresql.ENUM(
                "hotel",
                "transport",
                "venue",
                "referee",
                "guide",
                "club",
                name="provider_kind",
                create_type=False,
            ),
            nullable=False,
        ),
        sa.Column("city", sa.Text(), nullable=False),
        sa.Column("country", sa.Text(), nullable=False),
        sa.Column("contact", sa.Text(), nullable=False),
        sa.Column("unit_price_usd", sa.Integer(), nullable=False),
        sa.Column("unit", sa.Text(), nullable=False),
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("tenant_id", sa.UUID(), nullable=False),
        sa.ForeignKeyConstraint(
            ["tenant_id"],
            ["tenants.id"],
            name=op.f("fk_providers_tenant_id_tenants"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_providers")),
    )
    op.create_index(
        "ix_providers_tenant_kind_city", "providers", ["tenant_id", "kind", "city"], unique=False
    )
    op.create_table(
        "retrieval_eval_runs",
        sa.Column("embedding_model", sa.Text(), nullable=False),
        sa.Column("reranker", sa.Text(), nullable=True),
        sa.Column("dataset_version", sa.Text(), nullable=False),
        sa.Column("metrics", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("git_sha", sa.String(length=40), nullable=True),
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("tenant_id", sa.UUID(), nullable=False),
        sa.ForeignKeyConstraint(
            ["tenant_id"],
            ["tenants.id"],
            name=op.f("fk_retrieval_eval_runs_tenant_id_tenants"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_retrieval_eval_runs")),
    )
    op.create_index(
        "ix_retrieval_eval_runs_tenant_created",
        "retrieval_eval_runs",
        ["tenant_id", "created_at"],
        unique=False,
    )
    op.create_table(
        "users",
        sa.Column("email", sa.Text(), nullable=False),
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column(
            "role",
            postgresql.ENUM("owner", "ops", "sales", "viewer", name="user_role", create_type=False),
            nullable=False,
        ),
        sa.Column("auth_subject", sa.Text(), nullable=True),
        sa.Column("last_seen_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("tenant_id", sa.UUID(), nullable=False),
        sa.ForeignKeyConstraint(
            ["tenant_id"],
            ["tenants.id"],
            name=op.f("fk_users_tenant_id_tenants"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_users")),
    )
    op.create_index("uq_users_tenant_email", "users", ["tenant_id", "email"], unique=True)
    op.create_table(
        "accounts",
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column(
            "kind",
            postgresql.ENUM(
                "university",
                "club",
                "high_school",
                "family_group",
                name="account_kind",
                create_type=False,
            ),
            nullable=False,
        ),
        sa.Column("country", sa.Text(), nullable=False),
        sa.Column("state", sa.Text(), nullable=True),
        sa.Column("city", sa.Text(), nullable=True),
        sa.Column(
            "sport_programs", postgresql.ARRAY(sa.Text()), server_default="{}", nullable=False
        ),
        sa.Column("tier", sa.Text(), nullable=True),
        sa.Column("owner_user_id", sa.UUID(), nullable=True),
        sa.Column(
            "status",
            postgresql.ENUM(
                "prospect", "active", "past", "churned", name="account_status", create_type=False
            ),
            server_default="prospect",
            nullable=False,
        ),
        sa.Column(
            "health",
            postgresql.ENUM("green", "amber", "red", name="account_health", create_type=False),
            server_default="green",
            nullable=False,
        ),
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("tenant_id", sa.UUID(), nullable=False),
        sa.ForeignKeyConstraint(
            ["owner_user_id"],
            ["users.id"],
            name=op.f("fk_accounts_owner_user_id_users"),
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id"],
            ["tenants.id"],
            name=op.f("fk_accounts_tenant_id_tenants"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_accounts")),
    )
    op.create_index(
        "ix_accounts_tenant_status_health",
        "accounts",
        ["tenant_id", "status", "health"],
        unique=False,
    )
    op.create_index("uq_accounts_tenant_name", "accounts", ["tenant_id", "name"], unique=True)
    op.create_table(
        "api_keys",
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column("hash", sa.String(length=64), nullable=False),
        sa.Column("prefix", sa.String(length=16), nullable=False),
        sa.Column("scopes", postgresql.ARRAY(sa.Text()), server_default="{}", nullable=False),
        sa.Column("created_by", sa.UUID(), nullable=True),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("tenant_id", sa.UUID(), nullable=False),
        sa.ForeignKeyConstraint(
            ["created_by"],
            ["users.id"],
            name=op.f("fk_api_keys_created_by_users"),
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id"],
            ["tenants.id"],
            name=op.f("fk_api_keys_tenant_id_tenants"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_api_keys")),
        sa.UniqueConstraint("hash", name=op.f("uq_api_keys_hash")),
    )
    op.create_index("ix_api_keys_tenant_prefix", "api_keys", ["tenant_id", "prefix"], unique=False)
    op.create_table(
        "experiences",
        sa.Column("title", sa.Text(), nullable=False),
        sa.Column("city", sa.Text(), nullable=False),
        sa.Column("country", sa.Text(), nullable=False),
        sa.Column("sports", postgresql.ARRAY(sa.Text()), server_default="{}", nullable=False),
        sa.Column("duration_hours", sa.Float(), nullable=False),
        sa.Column("price_usd", sa.Integer(), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("provider_id", sa.UUID(), nullable=True),
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("tenant_id", sa.UUID(), nullable=False),
        sa.ForeignKeyConstraint(
            ["provider_id"],
            ["providers.id"],
            name=op.f("fk_experiences_provider_id_providers"),
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id"],
            ["tenants.id"],
            name=op.f("fk_experiences_tenant_id_tenants"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_experiences")),
    )
    op.create_index(
        "ix_experiences_sports", "experiences", ["sports"], unique=False, postgresql_using="gin"
    )
    op.create_index(
        "ix_experiences_tenant_country", "experiences", ["tenant_id", "country"], unique=False
    )
    op.create_table(
        "flows",
        sa.Column("key", sa.String(length=100), nullable=False),
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column("description", sa.Text(), server_default="", nullable=False),
        sa.Column("draft_graph", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("draft_revision", sa.Integer(), server_default="1", nullable=False),
        sa.Column("draft_updated_by", sa.UUID(), nullable=True),
        sa.Column("published_version_id", sa.UUID(), nullable=True),
        sa.Column("archived_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("tenant_id", sa.UUID(), nullable=False),
        sa.ForeignKeyConstraint(
            ["draft_updated_by"],
            ["users.id"],
            name=op.f("fk_flows_draft_updated_by_users"),
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id"],
            ["tenants.id"],
            name=op.f("fk_flows_tenant_id_tenants"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_flows")),
    )
    op.create_index("uq_flows_tenant_key", "flows", ["tenant_id", "key"], unique=True)
    op.create_table(
        "ingestion_jobs",
        sa.Column("document_id", sa.UUID(), nullable=False),
        sa.Column("temporal_workflow_id", sa.Text(), nullable=True),
        sa.Column(
            "status",
            postgresql.ENUM(
                "queued",
                "parsing",
                "chunking",
                "embedding",
                "indexing",
                "succeeded",
                "failed",
                name="ingestion_status",
                create_type=False,
            ),
            server_default="queued",
            nullable=False,
        ),
        sa.Column("embedding_model", sa.Text(), nullable=True),
        sa.Column(
            "stats", postgresql.JSONB(astext_type=sa.Text()), server_default="{}", nullable=False
        ),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column(
            "started_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("tenant_id", sa.UUID(), nullable=False),
        sa.ForeignKeyConstraint(
            ["document_id"],
            ["documents.id"],
            name=op.f("fk_ingestion_jobs_document_id_documents"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id"],
            ["tenants.id"],
            name=op.f("fk_ingestion_jobs_tenant_id_tenants"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_ingestion_jobs")),
    )
    op.create_index(
        "ix_ingestion_jobs_document", "ingestion_jobs", ["document_id", "started_at"], unique=False
    )
    op.create_table(
        "opponents",
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column("city", sa.Text(), nullable=False),
        sa.Column("country", sa.Text(), nullable=False),
        sa.Column(
            "sport",
            postgresql.ENUM(
                "soccer",
                "rugby",
                "field_hockey",
                "volleyball",
                "basketball",
                name="sport",
                create_type=False,
            ),
            nullable=False,
        ),
        sa.Column(
            "gender",
            postgresql.ENUM("men", "women", "mixed", name="gender", create_type=False),
            nullable=False,
        ),
        sa.Column("age_groups", postgresql.ARRAY(sa.Text()), nullable=False),
        sa.Column("level_score", sa.Integer(), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("provider_id", sa.UUID(), nullable=True),
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("tenant_id", sa.UUID(), nullable=False),
        sa.CheckConstraint(
            "level_score BETWEEN 1 AND 10", name=op.f("ck_opponents_level_score_range")
        ),
        sa.ForeignKeyConstraint(
            ["provider_id"],
            ["providers.id"],
            name=op.f("fk_opponents_provider_id_providers"),
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id"],
            ["tenants.id"],
            name=op.f("fk_opponents_tenant_id_tenants"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_opponents")),
    )
    op.create_index(
        "ix_opponents_age_groups", "opponents", ["age_groups"], unique=False, postgresql_using="gin"
    )
    op.create_index(
        "ix_opponents_tenant_filters",
        "opponents",
        ["tenant_id", "sport", "gender", "country"],
        unique=False,
    )
    op.create_table(
        "contacts",
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column("email", sa.Text(), nullable=True),
        sa.Column("phone", sa.Text(), nullable=True),
        sa.Column("organization", sa.Text(), nullable=True),
        sa.Column("role", sa.Text(), nullable=True),
        sa.Column("account_id", sa.UUID(), nullable=True),
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("tenant_id", sa.UUID(), nullable=False),
        sa.ForeignKeyConstraint(
            ["account_id"],
            ["accounts.id"],
            name=op.f("fk_contacts_account_id_accounts"),
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id"],
            ["tenants.id"],
            name=op.f("fk_contacts_tenant_id_tenants"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_contacts")),
    )
    op.create_index("ix_contacts_account", "contacts", ["account_id"], unique=False)
    op.create_index("ix_contacts_tenant_email", "contacts", ["tenant_id", "email"], unique=False)
    op.create_table(
        "flow_triggers",
        sa.Column("flow_id", sa.UUID(), nullable=False),
        sa.Column(
            "kind",
            postgresql.ENUM(
                "chat",
                "webhook",
                "schedule",
                "event",
                "manual",
                name="trigger_kind",
                create_type=False,
            ),
            nullable=False,
        ),
        sa.Column(
            "config", postgresql.JSONB(astext_type=sa.Text()), server_default="{}", nullable=False
        ),
        sa.Column("enabled", sa.Boolean(), server_default=sa.text("true"), nullable=False),
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("tenant_id", sa.UUID(), nullable=False),
        sa.ForeignKeyConstraint(
            ["flow_id"],
            ["flows.id"],
            name=op.f("fk_flow_triggers_flow_id_flows"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id"],
            ["tenants.id"],
            name=op.f("fk_flow_triggers_tenant_id_tenants"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_flow_triggers")),
    )
    op.create_index(
        "ix_flow_triggers_config", "flow_triggers", ["config"], unique=False, postgresql_using="gin"
    )
    op.create_index(
        "ix_flow_triggers_tenant_kind_enabled",
        "flow_triggers",
        ["tenant_id", "kind", "enabled"],
        unique=False,
    )
    op.create_table(
        "flow_versions",
        sa.Column("flow_id", sa.UUID(), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("graph", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("graph_hash", sa.String(length=64), nullable=False),
        sa.Column("schema_version", sa.String(length=20), nullable=False),
        sa.Column("published_by", sa.UUID(), nullable=True),
        sa.Column(
            "published_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("changelog", sa.Text(), server_default="", nullable=False),
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("tenant_id", sa.UUID(), nullable=False),
        sa.ForeignKeyConstraint(
            ["flow_id"],
            ["flows.id"],
            name=op.f("fk_flow_versions_flow_id_flows"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["published_by"],
            ["users.id"],
            name=op.f("fk_flow_versions_published_by_users"),
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id"],
            ["tenants.id"],
            name=op.f("fk_flow_versions_tenant_id_tenants"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_flow_versions")),
        sa.UniqueConstraint("flow_id", "version", name=op.f("uq_flow_versions_flow_id_version")),
    )
    # flows <-> flow_versions reference each other: add this FK once both tables exist.
    op.create_foreign_key(
        op.f("fk_flows_published_version_id_flow_versions"),
        "flows",
        "flow_versions",
        ["published_version_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_table(
        "flow_executions",
        sa.Column("flow_version_id", sa.UUID(), nullable=False),
        sa.Column(
            "trigger_kind",
            postgresql.ENUM(
                "chat",
                "webhook",
                "schedule",
                "event",
                "manual",
                name="trigger_kind",
                create_type=False,
            ),
            nullable=False,
        ),
        sa.Column(
            "trigger_payload",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default="{}",
            nullable=False,
        ),
        sa.Column(
            "status",
            postgresql.ENUM(
                "running",
                "waiting",
                "succeeded",
                "failed",
                "cancelled",
                name="execution_status",
                create_type=False,
            ),
            server_default="running",
            nullable=False,
        ),
        sa.Column("temporal_workflow_id", sa.Text(), nullable=False),
        sa.Column("temporal_run_id", sa.Text(), nullable=True),
        sa.Column(
            "vars", postgresql.JSONB(astext_type=sa.Text()), server_default="{}", nullable=False
        ),
        sa.Column("error", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column(
            "started_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("parent_execution_id", sa.UUID(), nullable=True),
        sa.Column("subject_type", sa.String(length=40), nullable=True),
        sa.Column("subject_id", sa.UUID(), nullable=True),
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("tenant_id", sa.UUID(), nullable=False),
        sa.ForeignKeyConstraint(
            ["flow_version_id"],
            ["flow_versions.id"],
            name=op.f("fk_flow_executions_flow_version_id_flow_versions"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["parent_execution_id"],
            ["flow_executions.id"],
            name=op.f("fk_flow_executions_parent_execution_id_flow_executions"),
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id"],
            ["tenants.id"],
            name=op.f("fk_flow_executions_tenant_id_tenants"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_flow_executions")),
        sa.UniqueConstraint(
            "temporal_workflow_id", name=op.f("uq_flow_executions_temporal_workflow_id")
        ),
    )
    op.create_index(
        "ix_flow_executions_subject",
        "flow_executions",
        ["subject_type", "subject_id"],
        unique=False,
    )
    op.create_index(
        "ix_flow_executions_tenant_status", "flow_executions", ["tenant_id", "status"], unique=False
    )
    op.create_index(
        "ix_flow_executions_tenant_version_started",
        "flow_executions",
        ["tenant_id", "flow_version_id", sa.literal_column("started_at DESC")],
        unique=False,
    )
    op.create_table(
        "stakeholders",
        sa.Column("account_id", sa.UUID(), nullable=False),
        sa.Column("contact_id", sa.UUID(), nullable=True),
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column("title", sa.Text(), nullable=True),
        sa.Column(
            "role",
            postgresql.ENUM(
                "decision_maker",
                "champion",
                "coach",
                "assistant_coach",
                "athletic_director",
                "compliance",
                "travel_coordinator",
                "finance",
                "parent_liaison",
                "other",
                name="stakeholder_role",
                create_type=False,
            ),
            nullable=False,
        ),
        sa.Column("influence", sa.Integer(), server_default="3", nullable=False),
        sa.Column(
            "sentiment",
            postgresql.ENUM(
                "positive", "neutral", "negative", "unknown", name="sentiment", create_type=False
            ),
            server_default="unknown",
            nullable=False,
        ),
        sa.Column("email", sa.Text(), nullable=True),
        sa.Column("phone", sa.Text(), nullable=True),
        sa.Column(
            "preferred_channel",
            postgresql.ENUM(
                "email",
                "call",
                "meeting",
                "chat",
                "whatsapp",
                "note",
                name="interaction_channel",
                create_type=False,
            ),
            nullable=True,
        ),
        sa.Column("last_contact_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("tenant_id", sa.UUID(), nullable=False),
        sa.CheckConstraint(
            "influence BETWEEN 1 AND 5", name=op.f("ck_stakeholders_influence_range")
        ),
        sa.ForeignKeyConstraint(
            ["account_id"],
            ["accounts.id"],
            name=op.f("fk_stakeholders_account_id_accounts"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["contact_id"],
            ["contacts.id"],
            name=op.f("fk_stakeholders_contact_id_contacts"),
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id"],
            ["tenants.id"],
            name=op.f("fk_stakeholders_tenant_id_tenants"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_stakeholders")),
    )
    op.create_index("ix_stakeholders_account", "stakeholders", ["account_id"], unique=False)
    op.create_index(
        "ix_stakeholders_tenant_email", "stakeholders", ["tenant_id", "email"], unique=False
    )
    op.create_table(
        "approvals",
        sa.Column("execution_id", sa.UUID(), nullable=True),
        sa.Column("node_id", sa.String(length=100), nullable=True),
        sa.Column("title", sa.Text(), nullable=False),
        sa.Column(
            "details", postgresql.JSONB(astext_type=sa.Text()), server_default="{}", nullable=False
        ),
        sa.Column("proposed_action", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("payload_hash", sa.String(length=80), nullable=False),
        sa.Column(
            "risk_class",
            postgresql.ENUM(
                "read", "internal_write", "external", name="tool_class", create_type=False
            ),
            nullable=False,
        ),
        sa.Column(
            "assignee_role",
            postgresql.ENUM("owner", "ops", "sales", "viewer", name="user_role", create_type=False),
            nullable=False,
        ),
        sa.Column("assignee_user_id", sa.UUID(), nullable=True),
        sa.Column(
            "status",
            postgresql.ENUM(
                "pending",
                "approved",
                "rejected",
                "expired",
                "superseded",
                name="approval_status",
                create_type=False,
            ),
            server_default="pending",
            nullable=False,
        ),
        sa.Column("decided_by", sa.UUID(), nullable=True),
        sa.Column("decided_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("comment", sa.Text(), nullable=True),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("superseded_by", sa.UUID(), nullable=True),
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("tenant_id", sa.UUID(), nullable=False),
        sa.ForeignKeyConstraint(
            ["assignee_user_id"],
            ["users.id"],
            name=op.f("fk_approvals_assignee_user_id_users"),
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["decided_by"],
            ["users.id"],
            name=op.f("fk_approvals_decided_by_users"),
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["execution_id"],
            ["flow_executions.id"],
            name=op.f("fk_approvals_execution_id_flow_executions"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["superseded_by"],
            ["approvals.id"],
            name=op.f("fk_approvals_superseded_by_approvals"),
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id"],
            ["tenants.id"],
            name=op.f("fk_approvals_tenant_id_tenants"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_approvals")),
    )
    op.create_index("ix_approvals_execution", "approvals", ["execution_id"], unique=False)
    op.create_index(
        "ix_approvals_inbox",
        "approvals",
        ["tenant_id", "assignee_role"],
        unique=False,
        postgresql_where="status = 'pending'",
    )
    op.create_table(
        "conversations",
        sa.Column(
            "channel",
            postgresql.ENUM("web", "whatsapp", "email", "mcp", name="channel", create_type=False),
            nullable=False,
        ),
        sa.Column("contact_id", sa.UUID(), nullable=True),
        sa.Column("is_simulation", sa.Boolean(), server_default=sa.text("false"), nullable=False),
        sa.Column("flow_execution_id", sa.UUID(), nullable=True),
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("tenant_id", sa.UUID(), nullable=False),
        sa.ForeignKeyConstraint(
            ["contact_id"],
            ["contacts.id"],
            name=op.f("fk_conversations_contact_id_contacts"),
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["flow_execution_id"],
            ["flow_executions.id"],
            name=op.f("fk_conversations_flow_execution_id_flow_executions"),
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id"],
            ["tenants.id"],
            name=op.f("fk_conversations_tenant_id_tenants"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_conversations")),
    )
    op.create_index(
        "ix_conversations_tenant_created",
        "conversations",
        ["tenant_id", "created_at"],
        unique=False,
    )
    op.create_table(
        "flow_node_runs",
        sa.Column("execution_id", sa.UUID(), nullable=False),
        sa.Column("node_id", sa.String(length=100), nullable=False),
        sa.Column("node_type", sa.String(length=60), nullable=False),
        sa.Column("attempt", sa.Integer(), server_default="1", nullable=False),
        sa.Column(
            "status",
            postgresql.ENUM(
                "running",
                "succeeded",
                "failed",
                "skipped",
                "waiting",
                name="node_run_status",
                create_type=False,
            ),
            nullable=False,
        ),
        sa.Column("input", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("output", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("error", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column(
            "started_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("duration_ms", sa.Integer(), nullable=True),
        sa.Column("idempotency_key", sa.Text(), nullable=False),
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("tenant_id", sa.UUID(), nullable=False),
        sa.ForeignKeyConstraint(
            ["execution_id"],
            ["flow_executions.id"],
            name=op.f("fk_flow_node_runs_execution_id_flow_executions"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id"],
            ["tenants.id"],
            name=op.f("fk_flow_node_runs_tenant_id_tenants"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_flow_node_runs")),
        sa.UniqueConstraint("idempotency_key", name=op.f("uq_flow_node_runs_idempotency_key")),
    )
    op.create_index(
        "ix_flow_node_runs_execution_started",
        "flow_node_runs",
        ["execution_id", "started_at"],
        unique=False,
    )
    op.create_table(
        "agent_runs",
        sa.Column("conversation_id", sa.UUID(), nullable=True),
        sa.Column("flow_node_run_id", sa.UUID(), nullable=True),
        sa.Column(
            "surface",
            postgresql.ENUM(
                "chat", "flow", "mcp", "copilot", "eval", name="agent_surface", create_type=False
            ),
            nullable=False,
        ),
        sa.Column("model", sa.Text(), nullable=False),
        sa.Column(
            "started_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("latency_ms", sa.Integer(), nullable=True),
        sa.Column("input_tokens", sa.Integer(), server_default="0", nullable=False),
        sa.Column("output_tokens", sa.Integer(), server_default="0", nullable=False),
        sa.Column("cache_read_tokens", sa.Integer(), server_default="0", nullable=False),
        sa.Column("cache_write_tokens", sa.Integer(), server_default="0", nullable=False),
        sa.Column(
            "cost_usd", sa.Numeric(precision=10, scale=6), server_default="0", nullable=False
        ),
        sa.Column("stop_reason", sa.Text(), nullable=True),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column("trace_id", sa.String(length=32), nullable=True),
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("tenant_id", sa.UUID(), nullable=False),
        sa.ForeignKeyConstraint(
            ["conversation_id"],
            ["conversations.id"],
            name=op.f("fk_agent_runs_conversation_id_conversations"),
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id"],
            ["tenants.id"],
            name=op.f("fk_agent_runs_tenant_id_tenants"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_agent_runs")),
    )
    op.create_index("ix_agent_runs_conversation", "agent_runs", ["conversation_id"], unique=False)
    op.create_index(
        "ix_agent_runs_tenant_surface_started",
        "agent_runs",
        ["tenant_id", "surface", sa.literal_column("started_at DESC")],
        unique=False,
    )
    op.create_table(
        "leads",
        sa.Column("contact_id", sa.UUID(), nullable=True),
        sa.Column("account_id", sa.UUID(), nullable=True),
        sa.Column("conversation_id", sa.UUID(), nullable=True),
        sa.Column(
            "sport",
            postgresql.ENUM(
                "soccer",
                "rugby",
                "field_hockey",
                "volleyball",
                "basketball",
                name="sport",
                create_type=False,
            ),
            nullable=False,
        ),
        sa.Column(
            "gender",
            postgresql.ENUM("men", "women", "mixed", name="gender", create_type=False),
            nullable=False,
        ),
        sa.Column("age_group", sa.Text(), nullable=False),
        sa.Column("level_score", sa.Integer(), nullable=False),
        sa.Column("group_size", sa.Integer(), nullable=False),
        sa.Column("destination_country", sa.Text(), nullable=False),
        sa.Column("travel_start", sa.Date(), nullable=False),
        sa.Column("duration_days", sa.Integer(), nullable=False),
        sa.Column("budget_per_person_usd", sa.Integer(), nullable=True),
        sa.Column("goals", sa.Text(), nullable=True),
        sa.Column(
            "status",
            postgresql.ENUM(
                "new",
                "qualified",
                "proposal_sent",
                "won",
                "lost",
                name="lead_status",
                create_type=False,
            ),
            server_default="new",
            nullable=False,
        ),
        sa.Column(
            "source",
            postgresql.ENUM(
                "chat", "webhook", "manual", "flow", name="lead_source", create_type=False
            ),
            server_default="manual",
            nullable=False,
        ),
        sa.Column("lost_reason", sa.Text(), nullable=True),
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("tenant_id", sa.UUID(), nullable=False),
        sa.CheckConstraint("group_size > 0", name=op.f("ck_leads_group_size_positive")),
        sa.CheckConstraint("level_score BETWEEN 1 AND 10", name=op.f("ck_leads_level_score_range")),
        sa.ForeignKeyConstraint(
            ["account_id"],
            ["accounts.id"],
            name=op.f("fk_leads_account_id_accounts"),
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["contact_id"],
            ["contacts.id"],
            name=op.f("fk_leads_contact_id_contacts"),
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["conversation_id"],
            ["conversations.id"],
            name=op.f("fk_leads_conversation_id_conversations"),
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id"],
            ["tenants.id"],
            name=op.f("fk_leads_tenant_id_tenants"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_leads")),
    )
    op.create_index("ix_leads_account", "leads", ["account_id"], unique=False)
    op.create_index(
        "ix_leads_tenant_status_created",
        "leads",
        ["tenant_id", "status", sa.literal_column("created_at DESC")],
        unique=False,
    )
    op.create_table(
        "messages",
        sa.Column("conversation_id", sa.UUID(), nullable=False),
        sa.Column(
            "role",
            postgresql.ENUM("user", "assistant", name="message_role", create_type=False),
            nullable=False,
        ),
        sa.Column("content", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("tenant_id", sa.UUID(), nullable=False),
        sa.ForeignKeyConstraint(
            ["conversation_id"],
            ["conversations.id"],
            name=op.f("fk_messages_conversation_id_conversations"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id"],
            ["tenants.id"],
            name=op.f("fk_messages_tenant_id_tenants"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_messages")),
    )
    op.create_index(
        "ix_messages_conversation_created",
        "messages",
        ["conversation_id", "created_at"],
        unique=False,
    )
    op.create_table(
        "agent_steps",
        sa.Column("run_id", sa.UUID(), nullable=False),
        sa.Column("idx", sa.Integer(), nullable=False),
        sa.Column("tool", sa.Text(), nullable=False),
        sa.Column("input", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("output", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("is_error", sa.Boolean(), server_default=sa.text("false"), nullable=False),
        sa.Column("duration_ms", sa.Integer(), nullable=False),
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("tenant_id", sa.UUID(), nullable=False),
        sa.ForeignKeyConstraint(
            ["run_id"],
            ["agent_runs.id"],
            name=op.f("fk_agent_steps_run_id_agent_runs"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id"],
            ["tenants.id"],
            name=op.f("fk_agent_steps_tenant_id_tenants"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_agent_steps")),
    )
    op.create_index("ix_agent_steps_run_idx", "agent_steps", ["run_id", "idx"], unique=False)
    op.create_table(
        "trips",
        sa.Column("lead_id", sa.UUID(), nullable=True),
        sa.Column("account_id", sa.UUID(), nullable=True),
        sa.Column("code", sa.Text(), nullable=True),
        sa.Column("title", sa.Text(), nullable=False),
        sa.Column("city", sa.Text(), nullable=False),
        sa.Column("country", sa.Text(), nullable=False),
        sa.Column("start_date", sa.Date(), nullable=False),
        sa.Column("end_date", sa.Date(), nullable=False),
        sa.Column(
            "status",
            postgresql.ENUM(
                "draft",
                "proposed",
                "confirmed",
                "in_progress",
                "completed",
                "cancelled",
                name="trip_status",
                create_type=False,
            ),
            server_default="draft",
            nullable=False,
        ),
        sa.Column("price_per_person_usd", sa.Integer(), nullable=False),
        sa.Column("summary", sa.Text(), server_default="", nullable=False),
        sa.Column(
            "pricing", postgresql.JSONB(astext_type=sa.Text()), server_default="{}", nullable=False
        ),
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("tenant_id", sa.UUID(), nullable=False),
        sa.CheckConstraint("end_date >= start_date", name=op.f("ck_trips_dates_ordered")),
        sa.ForeignKeyConstraint(
            ["account_id"],
            ["accounts.id"],
            name=op.f("fk_trips_account_id_accounts"),
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["lead_id"], ["leads.id"], name=op.f("fk_trips_lead_id_leads"), ondelete="SET NULL"
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id"],
            ["tenants.id"],
            name=op.f("fk_trips_tenant_id_tenants"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_trips")),
    )
    op.create_index("ix_trips_account", "trips", ["account_id"], unique=False)
    op.create_index("ix_trips_lead", "trips", ["lead_id"], unique=False)
    op.create_index(
        "ix_trips_tenant_status_start", "trips", ["tenant_id", "status", "start_date"], unique=False
    )
    op.create_table(
        "interactions",
        sa.Column("account_id", sa.UUID(), nullable=False),
        sa.Column("stakeholder_id", sa.UUID(), nullable=True),
        sa.Column(
            "channel",
            postgresql.ENUM(
                "email",
                "call",
                "meeting",
                "chat",
                "whatsapp",
                "note",
                name="interaction_channel",
                create_type=False,
            ),
            nullable=False,
        ),
        sa.Column(
            "direction",
            postgresql.ENUM("inbound", "outbound", "internal", name="direction", create_type=False),
            nullable=False,
        ),
        sa.Column("occurred_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("subject", sa.Text(), nullable=True),
        sa.Column("body", sa.Text(), nullable=False),
        sa.Column("trip_id", sa.UUID(), nullable=True),
        sa.Column("lead_id", sa.UUID(), nullable=True),
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("tenant_id", sa.UUID(), nullable=False),
        sa.ForeignKeyConstraint(
            ["account_id"],
            ["accounts.id"],
            name=op.f("fk_interactions_account_id_accounts"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["lead_id"],
            ["leads.id"],
            name=op.f("fk_interactions_lead_id_leads"),
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["stakeholder_id"],
            ["stakeholders.id"],
            name=op.f("fk_interactions_stakeholder_id_stakeholders"),
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id"],
            ["tenants.id"],
            name=op.f("fk_interactions_tenant_id_tenants"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["trip_id"],
            ["trips.id"],
            name=op.f("fk_interactions_trip_id_trips"),
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_interactions")),
    )
    op.create_index(
        "ix_interactions_account_occurred",
        "interactions",
        ["tenant_id", "account_id", "occurred_at"],
        unique=False,
    )
    op.create_index("ix_interactions_stakeholder", "interactions", ["stakeholder_id"], unique=False)
    op.create_table(
        "trip_items",
        sa.Column("trip_id", sa.UUID(), nullable=False),
        sa.Column("day", sa.Integer(), nullable=False),
        sa.Column(
            "slot",
            postgresql.ENUM("morning", "afternoon", "evening", name="item_slot", create_type=False),
            nullable=False,
        ),
        sa.Column(
            "kind",
            postgresql.ENUM(
                "arrival",
                "departure",
                "match",
                "training",
                "experience",
                "free",
                name="item_kind",
                create_type=False,
            ),
            nullable=False,
        ),
        sa.Column("title", sa.Text(), nullable=False),
        sa.Column("opponent_id", sa.UUID(), nullable=True),
        sa.Column("experience_id", sa.UUID(), nullable=True),
        sa.Column("provider_id", sa.UUID(), nullable=True),
        sa.Column(
            "status",
            postgresql.ENUM(
                "pending",
                "requested",
                "confirmed",
                "completed",
                "cancelled",
                name="item_status",
                create_type=False,
            ),
            server_default="pending",
            nullable=False,
        ),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("requested_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("confirmed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("result", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("tenant_id", sa.UUID(), nullable=False),
        sa.CheckConstraint("day >= 1", name=op.f("ck_trip_items_day_positive")),
        sa.ForeignKeyConstraint(
            ["experience_id"],
            ["experiences.id"],
            name=op.f("fk_trip_items_experience_id_experiences"),
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["opponent_id"],
            ["opponents.id"],
            name=op.f("fk_trip_items_opponent_id_opponents"),
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["provider_id"],
            ["providers.id"],
            name=op.f("fk_trip_items_provider_id_providers"),
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id"],
            ["tenants.id"],
            name=op.f("fk_trip_items_tenant_id_tenants"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["trip_id"], ["trips.id"], name=op.f("fk_trip_items_trip_id_trips"), ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_trip_items")),
    )
    op.create_index(
        "ix_trip_items_tenant_open",
        "trip_items",
        ["tenant_id", "status"],
        unique=False,
        postgresql_where="status IN ('pending', 'requested')",
    )
    op.create_index(
        "ix_trip_items_trip_day_slot", "trip_items", ["trip_id", "day", "slot"], unique=False
    )
    op.create_table(
        "account_facts",
        sa.Column("account_id", sa.UUID(), nullable=False),
        sa.Column(
            "kind",
            postgresql.ENUM(
                "status",
                "commitment",
                "risk",
                "preference",
                "budget",
                "decision",
                name="fact_kind",
                create_type=False,
            ),
            nullable=False,
        ),
        sa.Column("statement", sa.Text(), nullable=False),
        sa.Column("confidence", sa.Float(), nullable=False),
        sa.Column("source_interaction_id", sa.UUID(), nullable=False),
        sa.Column("valid_from", sa.DateTime(timezone=True), nullable=False),
        sa.Column("superseded_by", sa.UUID(), nullable=True),
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("tenant_id", sa.UUID(), nullable=False),
        sa.CheckConstraint(
            "confidence BETWEEN 0 AND 1", name=op.f("ck_account_facts_confidence_range")
        ),
        sa.ForeignKeyConstraint(
            ["account_id"],
            ["accounts.id"],
            name=op.f("fk_account_facts_account_id_accounts"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["source_interaction_id"],
            ["interactions.id"],
            name=op.f("fk_account_facts_source_interaction_id_interactions"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["superseded_by"],
            ["account_facts.id"],
            name=op.f("fk_account_facts_superseded_by_account_facts"),
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id"],
            ["tenants.id"],
            name=op.f("fk_account_facts_tenant_id_tenants"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_account_facts")),
    )
    op.create_index(
        "ix_account_facts_current",
        "account_facts",
        ["tenant_id", "account_id", "kind"],
        unique=False,
        postgresql_where="superseded_by IS NULL",
    )
    op.create_index(
        "ix_account_facts_source", "account_facts", ["source_interaction_id"], unique=False
    )
    op.create_table(
        "document_chunks",
        sa.Column("document_id", sa.UUID(), nullable=True),
        sa.Column("interaction_id", sa.UUID(), nullable=True),
        sa.Column("account_id", sa.UUID(), nullable=True),
        sa.Column("ordinal", sa.Integer(), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("token_count", sa.Integer(), nullable=False),
        sa.Column("heading_path", postgresql.ARRAY(sa.Text()), server_default="{}", nullable=False),
        sa.Column("content_hash", sa.String(length=64), nullable=False),
        sa.Column("vector_object_id", sa.String(length=63), nullable=True),
        sa.Column("quarantined", sa.Boolean(), server_default=sa.text("false"), nullable=False),
        sa.Column("quarantine_reason", sa.Text(), nullable=True),
        sa.Column("quarantined_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("reviewed_by", sa.UUID(), nullable=True),
        sa.Column("reviewed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("tenant_id", sa.UUID(), nullable=False),
        sa.CheckConstraint(
            "(document_id IS NULL) <> (interaction_id IS NULL)",
            name=op.f("ck_document_chunks_one_source"),
        ),
        sa.ForeignKeyConstraint(
            ["account_id"],
            ["accounts.id"],
            name=op.f("fk_document_chunks_account_id_accounts"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["document_id"],
            ["documents.id"],
            name=op.f("fk_document_chunks_document_id_documents"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["interaction_id"],
            ["interactions.id"],
            name=op.f("fk_document_chunks_interaction_id_interactions"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["reviewed_by"],
            ["users.id"],
            name=op.f("fk_document_chunks_reviewed_by_users"),
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id"],
            ["tenants.id"],
            name=op.f("fk_document_chunks_tenant_id_tenants"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_document_chunks")),
    )
    op.create_index(
        "ix_document_chunks_account", "document_chunks", ["tenant_id", "account_id"], unique=False
    )
    op.create_index(
        "ix_document_chunks_document_ordinal",
        "document_chunks",
        ["document_id", "ordinal"],
        unique=False,
    )
    op.create_index(
        "ix_document_chunks_quarantined",
        "document_chunks",
        ["tenant_id"],
        unique=False,
        postgresql_where="quarantined",
    )
    op.create_index(
        "uq_document_chunks_document_hash",
        "document_chunks",
        ["document_id", "content_hash"],
        unique=True,
    )
    op.create_index(
        "uq_document_chunks_interaction_hash",
        "document_chunks",
        ["interaction_id", "content_hash"],
        unique=True,
    )
    op.create_table(
        "incidents",
        sa.Column("trip_id", sa.UUID(), nullable=False),
        sa.Column("trip_item_id", sa.UUID(), nullable=True),
        sa.Column(
            "severity",
            postgresql.ENUM(
                "low", "medium", "high", "critical", name="incident_severity", create_type=False
            ),
            nullable=False,
        ),
        sa.Column("category", sa.Text(), nullable=False),
        sa.Column("title", sa.Text(), nullable=False),
        sa.Column("description", sa.Text(), server_default="", nullable=False),
        sa.Column(
            "status",
            postgresql.ENUM(
                "open", "mitigating", "resolved", name="incident_status", create_type=False
            ),
            server_default="open",
            nullable=False,
        ),
        sa.Column(
            "reported_by_type",
            postgresql.ENUM(
                "user", "agent", "flow", "api_key", "system", name="actor_type", create_type=False
            ),
            nullable=False,
        ),
        sa.Column("reported_by_id", sa.Text(), nullable=True),
        sa.Column("occurred_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("resolved_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("tenant_id", sa.UUID(), nullable=False),
        sa.ForeignKeyConstraint(
            ["tenant_id"],
            ["tenants.id"],
            name=op.f("fk_incidents_tenant_id_tenants"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["trip_id"], ["trips.id"], name=op.f("fk_incidents_trip_id_trips"), ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["trip_item_id"],
            ["trip_items.id"],
            name=op.f("fk_incidents_trip_item_id_trip_items"),
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_incidents")),
    )
    op.create_index(
        "ix_incidents_tenant_status_severity",
        "incidents",
        ["tenant_id", "status", "severity"],
        unique=False,
    )
    op.create_index("ix_incidents_trip", "incidents", ["trip_id"], unique=False)
    # ### end Alembic commands ###

    _enable_rls()


def downgrade() -> None:
    _disable_rls()

    # ### commands auto generated by Alembic - please adjust! ###
    op.drop_index("ix_incidents_trip", table_name="incidents")
    op.drop_index("ix_incidents_tenant_status_severity", table_name="incidents")
    op.drop_table("incidents")
    op.drop_index("uq_document_chunks_interaction_hash", table_name="document_chunks")
    op.drop_index("uq_document_chunks_document_hash", table_name="document_chunks")
    op.drop_index(
        "ix_document_chunks_quarantined",
        table_name="document_chunks",
        postgresql_where="quarantined",
    )
    op.drop_index("ix_document_chunks_document_ordinal", table_name="document_chunks")
    op.drop_index("ix_document_chunks_account", table_name="document_chunks")
    op.drop_table("document_chunks")
    op.drop_index("ix_account_facts_source", table_name="account_facts")
    op.drop_index(
        "ix_account_facts_current",
        table_name="account_facts",
        postgresql_where="superseded_by IS NULL",
    )
    op.drop_table("account_facts")
    op.drop_index("ix_trip_items_trip_day_slot", table_name="trip_items")
    op.drop_index(
        "ix_trip_items_tenant_open",
        table_name="trip_items",
        postgresql_where="status IN ('pending', 'requested')",
    )
    op.drop_table("trip_items")
    op.drop_index("ix_interactions_stakeholder", table_name="interactions")
    op.drop_index("ix_interactions_account_occurred", table_name="interactions")
    op.drop_table("interactions")
    op.drop_index("ix_trips_tenant_status_start", table_name="trips")
    op.drop_index("ix_trips_lead", table_name="trips")
    op.drop_index("ix_trips_account", table_name="trips")
    op.drop_table("trips")
    op.drop_index("ix_agent_steps_run_idx", table_name="agent_steps")
    op.drop_table("agent_steps")
    op.drop_index("ix_messages_conversation_created", table_name="messages")
    op.drop_table("messages")
    op.drop_index("ix_leads_tenant_status_created", table_name="leads")
    op.drop_index("ix_leads_account", table_name="leads")
    op.drop_table("leads")
    op.drop_index("ix_agent_runs_tenant_surface_started", table_name="agent_runs")
    op.drop_index("ix_agent_runs_conversation", table_name="agent_runs")
    op.drop_table("agent_runs")
    op.drop_index("ix_flow_node_runs_execution_started", table_name="flow_node_runs")
    op.drop_table("flow_node_runs")
    op.drop_index("ix_conversations_tenant_created", table_name="conversations")
    op.drop_table("conversations")
    op.drop_index(
        "ix_approvals_inbox", table_name="approvals", postgresql_where="status = 'pending'"
    )
    op.drop_index("ix_approvals_execution", table_name="approvals")
    op.drop_table("approvals")
    op.drop_index("ix_stakeholders_tenant_email", table_name="stakeholders")
    op.drop_index("ix_stakeholders_account", table_name="stakeholders")
    op.drop_table("stakeholders")
    op.drop_index("ix_flow_executions_tenant_version_started", table_name="flow_executions")
    op.drop_index("ix_flow_executions_tenant_status", table_name="flow_executions")
    op.drop_index("ix_flow_executions_subject", table_name="flow_executions")
    op.drop_table("flow_executions")
    op.drop_constraint(
        op.f("fk_flows_published_version_id_flow_versions"), "flows", type_="foreignkey"
    )
    op.drop_table("flow_versions")
    op.drop_index("ix_flow_triggers_tenant_kind_enabled", table_name="flow_triggers")
    op.drop_index("ix_flow_triggers_config", table_name="flow_triggers", postgresql_using="gin")
    op.drop_table("flow_triggers")
    op.drop_index("ix_contacts_tenant_email", table_name="contacts")
    op.drop_index("ix_contacts_account", table_name="contacts")
    op.drop_table("contacts")
    op.drop_index("ix_opponents_tenant_filters", table_name="opponents")
    op.drop_index("ix_opponents_age_groups", table_name="opponents", postgresql_using="gin")
    op.drop_table("opponents")
    op.drop_index("ix_ingestion_jobs_document", table_name="ingestion_jobs")
    op.drop_table("ingestion_jobs")
    op.drop_index("uq_flows_tenant_key", table_name="flows")
    op.drop_table("flows")
    op.drop_index("ix_experiences_tenant_country", table_name="experiences")
    op.drop_index("ix_experiences_sports", table_name="experiences", postgresql_using="gin")
    op.drop_table("experiences")
    op.drop_index("ix_api_keys_tenant_prefix", table_name="api_keys")
    op.drop_table("api_keys")
    op.drop_index("uq_accounts_tenant_name", table_name="accounts")
    op.drop_index("ix_accounts_tenant_status_health", table_name="accounts")
    op.drop_table("accounts")
    op.drop_index("uq_users_tenant_email", table_name="users")
    op.drop_table("users")
    op.drop_index("ix_retrieval_eval_runs_tenant_created", table_name="retrieval_eval_runs")
    op.drop_table("retrieval_eval_runs")
    op.drop_index("ix_providers_tenant_kind_city", table_name="providers")
    op.drop_table("providers")
    op.drop_index(
        "ix_outbox_events_pending",
        table_name="outbox_events",
        postgresql_where="dispatched_at IS NULL",
    )
    op.drop_table("outbox_events")
    op.drop_index("uq_documents_tenant_content_hash", table_name="documents")
    op.drop_index("ix_documents_tenant_status", table_name="documents")
    op.drop_table("documents")
    op.drop_index("ix_audit_log_subject", table_name="audit_log")
    op.drop_index("ix_audit_log_at_brin", table_name="audit_log", postgresql_using="brin")
    op.drop_table("audit_log")
    op.drop_table("tenants")
    # ### end Alembic commands ###

    for name in reversed(list(ENUMS)):
        postgresql.ENUM(name=name).drop(op.get_bind(), checkfirst=True)


def _create_app_role() -> None:
    # NOLOGIN group role. Local: the superuser SET ROLEs into it. Cloud SQL: the service
    # account's IAM user is granted membership by Terraform. Needs CREATEROLE on first run.
    create_role = """
        DO $$ BEGIN
            IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = '__APP_ROLE__') THEN
                CREATE ROLE __APP_ROLE__ NOLOGIN NOBYPASSRLS;
            END IF;
        END $$;
    """
    op.execute(create_role.replace("__APP_ROLE__", APP_ROLE))
    op.execute(f"GRANT USAGE ON SCHEMA public TO {APP_ROLE}")


def _enable_rls() -> None:
    for table in TENANT_TABLES:
        for stmt in _rls_on(table):
            op.execute(stmt)
    for table in UNSCOPED_TABLES:
        op.execute(f"GRANT SELECT ON {table} TO {APP_ROLE}")


def _disable_rls() -> None:
    for table in UNSCOPED_TABLES:
        op.execute(f"REVOKE ALL ON {table} FROM {APP_ROLE}")
    for table in TENANT_TABLES:
        for stmt in _rls_off(table):
            op.execute(stmt)
    # The role itself is left in place: other databases on the instance may use it.


def _rls_on(table: str) -> list[str]:
    predicate = f"tenant_id = NULLIF(current_setting('{TENANT_GUC}', true), '')::uuid"
    dml = "SELECT, INSERT" if table in APPEND_ONLY_TABLES else "SELECT, INSERT, UPDATE, DELETE"
    return [
        f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY",
        f"CREATE POLICY {table}_tenant_isolation ON {table} AS PERMISSIVE FOR ALL "
        f"TO {APP_ROLE} USING ({predicate}) WITH CHECK ({predicate})",
        f"GRANT {dml} ON {table} TO {APP_ROLE}",
    ]


def _rls_off(table: str) -> list[str]:
    return [
        f"DROP POLICY IF EXISTS {table}_tenant_isolation ON {table}",
        f"ALTER TABLE {table} DISABLE ROW LEVEL SECURITY",
        f"REVOKE ALL ON {table} FROM {APP_ROLE}",
    ]
