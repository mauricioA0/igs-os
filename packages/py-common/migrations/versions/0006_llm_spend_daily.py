"""Deployment-wide model spend per UTC day (readiness review B-01).

Backs ``igs_common.llm.budget``: every model call adds its cost here and calls are refused
once ``IGS_LLM_DAILY_BUDGET_USD`` is reached. Not tenant-scoped (one provider bill per
deployment), so no RLS policy; the app role may read and upsert it.

Revision ID: 0006
Revises: 0005
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0006"
down_revision: str | None = "0005"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

APP_ROLE = "igs_app"


def upgrade() -> None:
    op.create_table(
        "llm_spend_daily",
        sa.Column("day", sa.Date(), nullable=False),
        sa.Column("cost_usd", sa.Numeric(12, 6), server_default="0", nullable=False),
        sa.Column("calls", sa.Integer(), server_default="0", nullable=False),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("day", name=op.f("pk_llm_spend_daily")),
    )
    op.execute(f"GRANT SELECT, INSERT, UPDATE ON llm_spend_daily TO {APP_ROLE}")


def downgrade() -> None:
    op.drop_table("llm_spend_daily")
