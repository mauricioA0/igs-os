"""travelers: per-person trip roster (players, staff, parents), tenant-scoped with RLS.

Minors keep only a birth year and never their own email/phone (check `minor_no_contact`).

Revision ID: 0005
Revises: 0004
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0005"
down_revision: str | None = "0004"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# Inlined so this revision never changes behavior (see 0001).
APP_ROLE = "igs_app"
TENANT_GUC = "app.tenant_id"

traveler_role = postgresql.ENUM("player", "staff", "parent", name="traveler_role")


def upgrade() -> None:
    traveler_role.create(op.get_bind(), checkfirst=True)
    op.create_table(
        "travelers",
        sa.Column("trip_id", sa.UUID(), nullable=False),
        sa.Column("full_name", sa.Text(), nullable=False),
        sa.Column(
            "role",
            postgresql.ENUM(name="traveler_role", create_type=False),
            nullable=False,
        ),
        sa.Column("is_minor", sa.Boolean(), server_default=sa.text("false"), nullable=False),
        sa.Column("birth_year", sa.Integer(), nullable=True),
        sa.Column("email", sa.Text(), nullable=True),
        sa.Column("phone", sa.Text(), nullable=True),
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
            "NOT is_minor OR (email IS NULL AND phone IS NULL)",
            name="ck_travelers_minor_no_contact",
        ),
        sa.CheckConstraint(
            "birth_year IS NULL OR birth_year BETWEEN 1900 AND 2100",
            name="ck_travelers_birth_year_range",
        ),
        sa.ForeignKeyConstraint(
            ["trip_id"], ["trips.id"], name="fk_travelers_trip_id_trips", ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id"],
            ["tenants.id"],
            name="fk_travelers_tenant_id_tenants",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_travelers"),
    )
    op.create_index("ix_travelers_tenant_trip", "travelers", ["tenant_id", "trip_id"])
    predicate = f"tenant_id = NULLIF(current_setting('{TENANT_GUC}', true), '')::uuid"
    for stmt in (
        "ALTER TABLE travelers ENABLE ROW LEVEL SECURITY",
        f"CREATE POLICY travelers_tenant_isolation ON travelers AS PERMISSIVE FOR ALL "
        f"TO {APP_ROLE} USING ({predicate}) WITH CHECK ({predicate})",
        f"GRANT SELECT, INSERT, UPDATE, DELETE ON travelers TO {APP_ROLE}",
    ):
        op.execute(stmt)


def downgrade() -> None:
    op.execute("DROP POLICY IF EXISTS travelers_tenant_isolation ON travelers")
    op.execute(f"REVOKE ALL ON travelers FROM {APP_ROLE}")
    op.drop_index("ix_travelers_tenant_trip", table_name="travelers")
    op.drop_table("travelers")
    traveler_role.drop(op.get_bind(), checkfirst=True)
