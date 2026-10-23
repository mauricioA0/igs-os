"""``PaymentReminders``: the daily payment-schedule run for one tenant (task queue ``flows``).

Two Temporal Schedules drive it (``igs_common.payments.temporal.ensure_payment_schedules``):

* every day at 09:00 Buenos Aires — scan schedules, draft reminders, queue approvals, release
  the approved ones;
* every 10 minutes — release only, so an email approved at 09:05 leaves at 09:10, not tomorrow.

"Today" comes from ``workflow.now()`` in Buenos Aires, so a replay sees the same day.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import timedelta

from temporalio import workflow
from temporalio.common import RetryPolicy

with workflow.unsafe.imports_passed_through():
    from igs_common.payments.schedule import ops_today

    from ..activities.payments import PaymentRunInput, QueueRemindersResult

_RETRY = RetryPolicy(
    initial_interval=timedelta(seconds=5),
    maximum_interval=timedelta(minutes=5),
    maximum_attempts=5,
)


@dataclass
class PaymentRemindersInput:
    tenant_id: str
    release_only: bool = False


@dataclass
class PaymentRemindersResult:
    today: str
    queued: QueueRemindersResult | None
    released: int


@workflow.defn(name="PaymentReminders")  # igs_common.payments.temporal.WORKFLOW_TYPE
class PaymentRemindersWorkflow:
    @workflow.run
    async def run(self, inp: PaymentRemindersInput) -> PaymentRemindersResult:
        today = ops_today(workflow.now()).isoformat()
        run = PaymentRunInput(inp.tenant_id, today)
        queued: QueueRemindersResult | None = None
        if not inp.release_only:
            queued = await workflow.execute_activity(
                "payments.queue_reminders",
                run,
                result_type=QueueRemindersResult,
                start_to_close_timeout=timedelta(minutes=10),
                retry_policy=_RETRY,
            )
        released: int = await workflow.execute_activity(
            "payments.release_approved",
            run,
            result_type=int,
            start_to_close_timeout=timedelta(minutes=2),
            retry_policy=_RETRY,
        )
        return PaymentRemindersResult(today, queued, released)


PAYMENT_WORKFLOWS = [PaymentRemindersWorkflow]
