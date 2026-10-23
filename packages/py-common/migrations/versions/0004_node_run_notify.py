"""Push notifications for the executions SSE: NOTIFY igs_node_runs '<execution_id>'.

Node runs are written by the worker; the API's stream (`GET /v1/executions/{id}/stream`)
listens on `igs_node_runs` with the execution id as payload and keeps its 2 s polling as a
fallback. Status changes on `flow_executions` notify too, so streams close as soon as an
execution ends. NOTIFY is transactional: listeners only hear about committed rows.

Revision ID: 0004
Revises: 0003
"""

from collections.abc import Sequence

from alembic import op

revision: str = "0004"
down_revision: str | None = "0003"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

CHANNEL = "igs_node_runs"


def upgrade() -> None:
    op.execute(
        f"""
        CREATE FUNCTION igs_notify_node_run() RETURNS trigger
        LANGUAGE plpgsql AS $$
        BEGIN
            PERFORM pg_notify('{CHANNEL}', NEW.execution_id::text);
            RETURN NULL;
        END $$;
        """
    )
    op.execute(
        """
        CREATE TRIGGER trg_flow_node_runs_notify
        AFTER INSERT OR UPDATE ON flow_node_runs
        FOR EACH ROW EXECUTE FUNCTION igs_notify_node_run();
        """
    )
    op.execute(
        f"""
        CREATE FUNCTION igs_notify_execution_status() RETURNS trigger
        LANGUAGE plpgsql AS $$
        BEGIN
            PERFORM pg_notify('{CHANNEL}', NEW.id::text);
            RETURN NULL;
        END $$;
        """
    )
    op.execute(
        """
        CREATE TRIGGER trg_flow_executions_notify
        AFTER UPDATE OF status ON flow_executions
        FOR EACH ROW WHEN (OLD.status IS DISTINCT FROM NEW.status)
        EXECUTE FUNCTION igs_notify_execution_status();
        """
    )


def downgrade() -> None:
    op.execute("DROP TRIGGER IF EXISTS trg_flow_executions_notify ON flow_executions")
    op.execute("DROP FUNCTION IF EXISTS igs_notify_execution_status()")
    op.execute("DROP TRIGGER IF EXISTS trg_flow_node_runs_notify ON flow_node_runs")
    op.execute("DROP FUNCTION IF EXISTS igs_notify_node_run()")
