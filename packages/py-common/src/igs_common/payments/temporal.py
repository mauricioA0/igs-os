"""Temporal Schedules for the ``PaymentReminders`` workflow (implemented in ``igs_worker``).

Referenced by name so the API and scripts can create schedules without importing the worker.
"""

from __future__ import annotations

from temporalio.client import (
    Client,
    Schedule,
    ScheduleActionStartWorkflow,
    ScheduleAlreadyRunningError,
    ScheduleOverlapPolicy,
    SchedulePolicy,
    ScheduleSpec,
)

WORKFLOW_TYPE = "PaymentReminders"
OPS_TIME_ZONE = "America/Argentina/Buenos_Aires"
DAILY_CRON = "0 9 * * *"  # scan + draft + queue approvals, 09:00 in Buenos Aires
RELEASE_CRON = "*/10 * * * *"  # release approved reminders to the outbox


def schedule_ids(tenant_id: str) -> tuple[str, str]:
    return f"payments-daily-{tenant_id}", f"payments-release-{tenant_id}"


async def ensure_payment_schedules(
    client: Client, tenant_id: str, *, task_queue: str = "flows"
) -> list[str]:
    """Create the daily and the release schedules for a tenant if missing (idempotent)."""
    daily, release = schedule_ids(tenant_id)
    specs = {
        daily: (DAILY_CRON, {"tenant_id": tenant_id, "release_only": False}),
        release: (RELEASE_CRON, {"tenant_id": tenant_id, "release_only": True}),
    }
    for schedule_id, (cron, arg) in specs.items():
        try:
            await client.create_schedule(
                schedule_id,
                Schedule(
                    action=ScheduleActionStartWorkflow(
                        WORKFLOW_TYPE, arg, id=f"{schedule_id}-run", task_queue=task_queue
                    ),
                    spec=ScheduleSpec(cron_expressions=[cron], time_zone_name=OPS_TIME_ZONE),
                    policy=SchedulePolicy(overlap=ScheduleOverlapPolicy.SKIP),
                ),
            )
        except ScheduleAlreadyRunningError:
            pass
    return list(specs)
