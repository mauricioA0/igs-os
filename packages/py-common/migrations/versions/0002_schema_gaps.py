"""schema gaps: approval subjects, trip owner/travelers, item time/alert, fact lifecycle,
account briefs, inline document content, pgvector + FTS on chunks, API-key lookup function

Revision ID: 0002
Revises: 0001
Create Date: 2026-10-22 23:30:00+00:00
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from pgvector.sqlalchemy import Vector
from sqlalchemy.dialects import postgresql

revision: str = "0002"
down_revision: str | None = "0001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


# Inlined so this revision never changes behavior (see 0001).
APP_ROLE = "igs_app"
TENANT_GUC = "app.tenant_id"
EMBEDDING_DIMS = 1024

fact_severity = postgresql.ENUM("low", "medium", "high", name="fact_severity", create_type=False)
fact_status = postgresql.ENUM("open", "done", "dropped", name="fact_status", create_type=False)

# Cross-tenant lookup by key hash, run before any tenant is known. SECURITY DEFINER executes as
# the owner (migration role), which RLS does not filter; it only ever returns active keys and
# never the hash itself.
RESOLVE_API_KEY = """
CREATE OR REPLACE FUNCTION resolve_api_key(p_hash text)
RETURNS TABLE (api_key_id uuid, tenant_id uuid, scopes text[], role text)
LANGUAGE sql STABLE SECURITY DEFINER
SET search_path = public, pg_temp
AS $$
    SELECT k.id, k.tenant_id, k.scopes, coalesce(u.role::text, 'viewer')
    FROM api_keys k
    LEFT JOIN users u ON u.id = k.created_by AND u.tenant_id = k.tenant_id
    WHERE k.hash = p_hash
      AND k.revoked_at IS NULL
      AND (k.expires_at IS NULL OR k.expires_at > now())
$$
"""


def upgrade() -> None:
    op.execute("CREATE EXTENSION IF NOT EXISTS vector")
    fact_severity.create(op.get_bind(), checkfirst=True)
    fact_status.create(op.get_bind(), checkfirst=True)

    # Approvals: what the decision is about.
    op.add_column("approvals", sa.Column("subject_type", sa.String(length=40), nullable=True))
    op.add_column("approvals", sa.Column("subject_id", sa.UUID(), nullable=True))
    op.create_index(
        "ix_approvals_subject", "approvals", ["tenant_id", "subject_type", "subject_id"]
    )

    # Trips: travelers and the ops owner.
    op.add_column("trips", sa.Column("travelers", sa.Integer(), nullable=True))
    op.add_column("trips", sa.Column("owner_user_id", sa.UUID(), nullable=True))
    op.create_foreign_key(
        "fk_trips_owner_user_id_users",
        "trips",
        "users",
        ["owner_user_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_check_constraint(
        "ck_trips_travelers_positive", "trips", "travelers IS NULL OR travelers > 0"
    )

    # Trip items: local time and an ops-facing alert.
    op.add_column("trip_items", sa.Column("time", sa.Time(), nullable=True))
    op.add_column("trip_items", sa.Column("alert", sa.Text(), nullable=True))

    # Account facts: lifecycle of risks and commitments.
    op.add_column("account_facts", sa.Column("severity", fact_severity, nullable=True))
    op.add_column("account_facts", sa.Column("due_date", sa.Date(), nullable=True))
    op.add_column(
        "account_facts",
        sa.Column("status", fact_status, server_default="open", nullable=False),
    )

    # Account briefs cache.
    op.create_table(
        "account_briefs",
        sa.Column("account_id", sa.UUID(), nullable=False),
        sa.Column("inputs_hash", sa.String(length=80), nullable=False),
        sa.Column("brief", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("model", sa.Text(), nullable=False),
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
            name="fk_account_briefs_account_id_accounts",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id"],
            ["tenants.id"],
            name="fk_account_briefs_tenant_id_tenants",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_account_briefs"),
    )
    op.create_index(
        "uq_account_briefs_account_inputs",
        "account_briefs",
        ["tenant_id", "account_id", "inputs_hash"],
        unique=True,
    )
    op.create_index(
        "ix_account_briefs_account_created",
        "account_briefs",
        ["tenant_id", "account_id", "created_at"],
    )
    for stmt in _rls_on("account_briefs"):
        op.execute(stmt)

    # Documents: small sources are stored inline until they move to GCS.
    op.add_column("documents", sa.Column("inline_content", sa.Text(), nullable=True))

    # Chunks: dense + sparse vectors and the keyword side of hybrid search.
    op.add_column("document_chunks", sa.Column("embedding", Vector(EMBEDDING_DIMS), nullable=True))
    op.add_column(
        "document_chunks",
        sa.Column("sparse", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
    )
    op.add_column(
        "document_chunks",
        sa.Column(
            "tsv",
            postgresql.TSVECTOR(),
            sa.Computed("to_tsvector('simple', content)", persisted=True),
            nullable=False,
        ),
    )
    op.create_index(
        "ix_document_chunks_embedding_hnsw",
        "document_chunks",
        ["embedding"],
        postgresql_using="hnsw",
        postgresql_ops={"embedding": "vector_cosine_ops"},
    )
    op.create_index("ix_document_chunks_tsv", "document_chunks", ["tsv"], postgresql_using="gin")

    # One statement per execute: asyncpg prepares each one.
    op.execute(RESOLVE_API_KEY)
    op.execute("REVOKE ALL ON FUNCTION resolve_api_key(text) FROM PUBLIC")
    op.execute(f"GRANT EXECUTE ON FUNCTION resolve_api_key(text) TO {APP_ROLE}")


def downgrade() -> None:
    op.execute("DROP FUNCTION IF EXISTS resolve_api_key(text)")

    op.drop_index("ix_document_chunks_tsv", table_name="document_chunks", postgresql_using="gin")
    op.drop_index(
        "ix_document_chunks_embedding_hnsw",
        table_name="document_chunks",
        postgresql_using="hnsw",
        postgresql_ops={"embedding": "vector_cosine_ops"},
    )
    op.drop_column("document_chunks", "tsv")
    op.drop_column("document_chunks", "sparse")
    op.drop_column("document_chunks", "embedding")
    op.drop_column("documents", "inline_content")

    for stmt in _rls_off("account_briefs"):
        op.execute(stmt)
    op.drop_index("ix_account_briefs_account_created", table_name="account_briefs")
    op.drop_index("uq_account_briefs_account_inputs", table_name="account_briefs")
    op.drop_table("account_briefs")

    op.drop_column("account_facts", "status")
    op.drop_column("account_facts", "due_date")
    op.drop_column("account_facts", "severity")

    op.drop_column("trip_items", "alert")
    op.drop_column("trip_items", "time")

    op.drop_constraint("ck_trips_travelers_positive", "trips", type_="check")
    op.drop_constraint("fk_trips_owner_user_id_users", "trips", type_="foreignkey")
    op.drop_column("trips", "owner_user_id")
    op.drop_column("trips", "travelers")

    op.drop_index("ix_approvals_subject", table_name="approvals")
    op.drop_column("approvals", "subject_id")
    op.drop_column("approvals", "subject_type")

    fact_status.drop(op.get_bind(), checkfirst=True)
    fact_severity.drop(op.get_bind(), checkfirst=True)
    # The vector extension stays: dropping it would fail if anything else in the database
    # uses it, and leaving it installed is harmless.


def _rls_on(table: str) -> list[str]:
    predicate = f"tenant_id = NULLIF(current_setting('{TENANT_GUC}', true), '')::uuid"
    return [
        f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY",
        f"CREATE POLICY {table}_tenant_isolation ON {table} AS PERMISSIVE FOR ALL "
        f"TO {APP_ROLE} USING ({predicate}) WITH CHECK ({predicate})",
        f"GRANT SELECT, INSERT, UPDATE, DELETE ON {table} TO {APP_ROLE}",
    ]


def _rls_off(table: str) -> list[str]:
    return [
        f"DROP POLICY IF EXISTS {table}_tenant_isolation ON {table}",
        f"ALTER TABLE {table} DISABLE ROW LEVEL SECURITY",
        f"REVOKE ALL ON {table} FROM {APP_ROLE}",
    ]
