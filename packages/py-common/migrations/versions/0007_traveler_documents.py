"""traveler_documents: pre-departure requirement status per traveler (status only, no files).

Revision ID: 0007
Revises: 0006
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0007"
down_revision: str | None = "0006"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# Inlined so this revision never changes behavior (see 0001).
APP_ROLE = "igs_app"
TENANT_GUC = "app.tenant_id"


def upgrade() -> None:
    op.create_table(
        "traveler_documents",
        sa.Column("traveler_id", sa.UUID(), nullable=False),
        sa.Column("requirement", sa.String(length=40), nullable=False),
        sa.Column("status", sa.String(length=20), server_default="missing", nullable=False),
        sa.Column("valid_from", sa.Date(), nullable=True),
        sa.Column("valid_until", sa.Date(), nullable=True),
        sa.Column("note", sa.Text(), nullable=True),
        sa.Column("updated_by", sa.UUID(), nullable=True),
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
            "status IN ('missing', 'requested', 'received', 'verified', 'not_applicable')",
            name="ck_traveler_documents_status_known",
        ),
        sa.CheckConstraint(
            "valid_until IS NULL OR valid_from IS NULL OR valid_until >= valid_from",
            name="ck_traveler_documents_validity_ordered",
        ),
        sa.ForeignKeyConstraint(
            ["traveler_id"],
            ["travelers.id"],
            name="fk_traveler_documents_traveler_id_travelers",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["updated_by"],
            ["users.id"],
            name="fk_traveler_documents_updated_by_users",
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id"],
            ["tenants.id"],
            name="fk_traveler_documents_tenant_id_tenants",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_traveler_documents"),
        sa.UniqueConstraint(
            "traveler_id", "requirement", name="uq_traveler_documents_traveler_id_requirement"
        ),
    )
    op.create_index(
        "ix_traveler_documents_tenant_traveler",
        "traveler_documents",
        ["tenant_id", "traveler_id"],
    )
    predicate = f"tenant_id = NULLIF(current_setting('{TENANT_GUC}', true), '')::uuid"
    for stmt in (
        "ALTER TABLE traveler_documents ENABLE ROW LEVEL SECURITY",
        f"CREATE POLICY traveler_documents_tenant_isolation ON traveler_documents AS PERMISSIVE "
        f"FOR ALL TO {APP_ROLE} USING ({predicate}) WITH CHECK ({predicate})",
        f"GRANT SELECT, INSERT, UPDATE, DELETE ON traveler_documents TO {APP_ROLE}",
    ):
        op.execute(stmt)


def downgrade() -> None:
    op.execute("DROP POLICY IF EXISTS traveler_documents_tenant_isolation ON traveler_documents")
    op.execute(f"REVOKE ALL ON traveler_documents FROM {APP_ROLE}")
    op.drop_index("ix_traveler_documents_tenant_traveler", table_name="traveler_documents")
    op.drop_table("traveler_documents")
