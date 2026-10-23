"""Reset the public demo and park a *live* Lakeshore flow on its ops approval.

1. ``igs_common.seed.reset_demo`` restores the demo tenant (visitor rows gone, fixtures back).
2. If Temporal is reachable, a real ``FlowExecution`` workflow is started for the seeded
   inquiry execution (``ex-lak-inbound``). It resumes from the seeded node outputs with the
   cursor on ``ops_review`` — nothing before the approval runs again, so no model is called —
   and waits there on approval ``a-9003``. Approving it in the inbox (or via the API) signals
   the workflow, which sends the proposal and finishes the execution.

The workflow id is the one the seed writes on the execution row, so the API's approval decision
reaches it without any extra linking. Re-running the script terminates the previous run.

    DATABASE_URL=postgres://igs:igs@localhost:5433/igs \\
    uv run python services/core/scripts/demo_reset.py            # needs `docker compose up -d`
    uv run python services/core/scripts/demo_reset.py --no-temporal   # data only
"""

import argparse
import asyncio
import sys
from collections.abc import Sequence
from typing import Any

from sqlalchemy import select
from temporalio.common import WorkflowIDConflictPolicy

from igs_common.db import system_scope
from igs_common.db.models import FlowExecution, FlowNodeRun, FlowVersion
from igs_common.db.session import configure
from igs_common.payments.temporal import ensure_payment_schedules
from igs_common.seed import fixture_id
from igs_common.seed.reset import reset_demo
from igs_common.temporal.client import connect_client
from igs_core.config import Settings
from igs_core.temporal import WORKFLOW_TYPE, data_converter, execution_input

TENANT = "igs"
EXECUTION_KEY = "ex-lak-inbound"
PARK_AT = "ops_review"


async def parked_input(execution_id: Any) -> tuple[str, dict[str, Any]]:
    """Workflow id + input that resumes the seeded execution right at ``PARK_AT``."""
    async with system_scope() as s:
        execution = await s.get(FlowExecution, execution_id)
        if execution is None:
            raise SystemExit(f"execution {EXECUTION_KEY} not seeded")
        version = await s.get(FlowVersion, execution.flow_version_id)
        assert version is not None
        runs = (
            await s.scalars(
                select(FlowNodeRun)
                .where(FlowNodeRun.execution_id == execution_id)
                .order_by(FlowNodeRun.started_at)
            )
        ).all()
    done = [r for r in runs if r.status == "succeeded"]
    payload = execution_input(
        execution_id=str(execution.id),
        tenant_id=str(execution.tenant_id),
        graph=version.graph,
        version=version.version,
        trigger={"type": execution.trigger_kind, **execution.trigger_payload},
        vars=execution.vars,
    )
    payload |= {
        # Continue-as-new state (see FlowExecutionWorkflow): where to start and what already ran.
        "cursor": PARK_AT,
        "nodes": {r.node_id: {"output": r.output} for r in done},
        "iterations": {r.node_id: 1 for r in done},
        "steps": len(done),
    }
    return execution.temporal_workflow_id, payload


async def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Reset the demo and park a live flow on its approval."
    )
    parser.add_argument("--no-temporal", action="store_true", help="reset data only")
    args = parser.parse_args(argv)

    configure()
    async with system_scope() as s:
        report = await reset_demo(s, tenant_slug=TENANT)
    print(f"demo data reset: {report}", file=sys.stderr)
    if args.no_temporal:
        return 0

    settings = Settings()
    try:
        client = await connect_client(
            settings.temporal_address,
            namespace=settings.temporal_namespace,
            data_converter=data_converter(settings),
        )
    except Exception as exc:  # Temporal is optional for a data-only demo
        print(
            f"temporal unreachable ({exc}); the approval won't resume a live flow", file=sys.stderr
        )
        return 0

    workflow_id, payload = await parked_input(fixture_id(TENANT, "execution", EXECUTION_KEY))
    handle = await client.start_workflow(
        WORKFLOW_TYPE,
        payload,
        id=workflow_id,
        task_queue=settings.temporal_task_queue_flows,
        id_conflict_policy=WorkflowIDConflictPolicy.TERMINATE_EXISTING,
    )
    print(f"live workflow {handle.id} parked at {PARK_AT}", file=sys.stderr)
    tenant_id = str(fixture_id(TENANT, "tenant", TENANT))
    schedules = await ensure_payment_schedules(
        client, tenant_id, task_queue=settings.temporal_task_queue_flows
    )
    print(f"payment reminder schedules: {', '.join(schedules)}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
