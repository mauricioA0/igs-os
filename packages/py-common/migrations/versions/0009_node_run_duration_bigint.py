"""flow_node_runs.duration_ms: integer → bigint.

A `wait` node can last months (pre-departure-check waits until 30 days before departure), and
int32 milliseconds overflow after ~24.8 days, so recording such a run failed.

Revision ID: 0009
Revises: 0008
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0009"
down_revision: str | None = "0008"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.alter_column(
        "flow_node_runs", "duration_ms", type_=sa.BigInteger(), existing_type=sa.Integer()
    )


def downgrade() -> None:
    op.alter_column(
        "flow_node_runs", "duration_ms", type_=sa.Integer(), existing_type=sa.BigInteger()
    )
