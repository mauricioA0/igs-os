"""Lead intake: site-form submissions and forwarded emails, scored, with a response clock.

Revision ID: 0008
Revises: 0007
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0008"
down_revision: str | None = "0007"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

TABLE = "lead_intakes"
# Inlined (not imported from igs_common.db.rls) so this revision never changes behavior.
APP_ROLE = "igs_app"
TENANT_GUC = "app.tenant_id"


def upgrade() -> None:
    op.create_table(
        TABLE,
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("channel", sa.Text(), nullable=False),
        sa.Column("status", sa.Text(), server_default="open", nullable=False),
        sa.Column("dedupe_key", sa.Text(), nullable=False),
        sa.Column("relationship", sa.Text(), server_default="new", nullable=False),
        sa.Column("contact_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("account_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("lead_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("approval_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column(
            "submitted",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default="{}",
            nullable=False,
        ),
        sa.Column("body_text", sa.Text(), server_default="", nullable=False),
        sa.Column(
            "extracted",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default="{}",
            nullable=False,
        ),
        sa.Column("missing", postgresql.ARRAY(sa.Text()), server_default="{}", nullable=False),
        sa.Column("score", sa.Integer(), server_default="0", nullable=False),
        sa.Column(
            "score_reasons",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default="[]",
            nullable=False,
        ),
        sa.Column("extraction_model", sa.Text(), nullable=True),
        sa.Column("received_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("sla_due_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("first_response_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint("channel IN ('form', 'email')", name="ck_lead_intakes_channel_known"),
        sa.CheckConstraint(
            "status IN ('open', 'lead_created', 'spam')", name="ck_lead_intakes_status_known"
        ),
        sa.CheckConstraint(
            "relationship IN ('new', 'known_contact', 'returning_customer', 'referral')",
            name="ck_lead_intakes_relationship_known",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id"],
            ["tenants.id"],
            name="fk_lead_intakes_tenant_id_tenants",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["contact_id"],
            ["contacts.id"],
            name="fk_lead_intakes_contact_id_contacts",
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["account_id"],
            ["accounts.id"],
            name="fk_lead_intakes_account_id_accounts",
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["lead_id"], ["leads.id"], name="fk_lead_intakes_lead_id_leads", ondelete="SET NULL"
        ),
        sa.ForeignKeyConstraint(
            ["approval_id"],
            ["approvals.id"],
            name="fk_lead_intakes_approval_id_approvals",
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_lead_intakes"),
    )
    op.create_index(
        "uq_lead_intakes_tenant_dedupe", TABLE, ["tenant_id", "dedupe_key"], unique=True
    )
    op.create_index(
        "ix_lead_intakes_tenant_status_due", TABLE, ["tenant_id", "status", "sla_due_at"]
    )
    op.create_index("ix_lead_intakes_contact", TABLE, ["contact_id"])
    for stmt in _rls_on(TABLE):
        op.execute(stmt)


def downgrade() -> None:
    for stmt in _rls_off(TABLE):
        op.execute(stmt)
    op.drop_table(TABLE)


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
