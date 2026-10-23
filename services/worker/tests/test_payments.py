"""PaymentReminders workflow with fake activities, and the activity against a real Postgres."""

import uuid
from collections.abc import AsyncIterator
from dataclasses import dataclass, field
from datetime import date

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncEngine
from sqlalchemy.pool import NullPool
from temporalio import activity
from temporalio.testing import WorkflowEnvironment
from temporalio.worker import Worker

from igs_common.db.models import Approval
from igs_common.db.session import create_engine, system_scope
from igs_common.llm import FakeLLM, Scripted
from igs_common.payments.reminders import DETAILS
from igs_common.seed import fixture_id, load
from igs_common.testing import DatabaseUnavailableError, database_url, prepare_database
from igs_worker.activities.payments import PaymentActivities, PaymentRunInput, QueueRemindersResult
from igs_worker.workflows.payments import (
    PaymentRemindersInput,
    PaymentRemindersWorkflow,
)


@dataclass
class FakePayments:
    calls: list[tuple[str, PaymentRunInput]] = field(default_factory=list)

    @activity.defn(name="payments.queue_reminders")
    async def queue_reminders(self, inp: PaymentRunInput) -> QueueRemindersResult:
        self.calls.append(("queue", inp))
        return QueueRemindersResult(trips=3, reminders=2, approvals_created=2)

    @activity.defn(name="payments.release_approved")
    async def release_approved(self, inp: PaymentRunInput) -> int:
        self.calls.append(("release", inp))
        return 1


async def _run(env: WorkflowEnvironment, inp: PaymentRemindersInput, fake: FakePayments):
    queue = f"payments-{uuid.uuid4()}"
    async with Worker(
        env.client,
        task_queue=queue,
        workflows=[PaymentRemindersWorkflow],
        activities=[fake.queue_reminders, fake.release_approved],
    ):
        return await env.client.execute_workflow(
            PaymentRemindersWorkflow.run,
            inp,
            id=f"pay-{uuid.uuid4()}",
            task_queue=queue,
        )


async def test_daily_run_queues_then_releases(env: WorkflowEnvironment) -> None:
    fake = FakePayments()
    result = await _run(env, PaymentRemindersInput("t-1"), fake)
    assert [c[0] for c in fake.calls] == ["queue", "release"]
    assert result.queued is not None and result.queued.approvals_created == 2
    assert result.released == 1
    # "today" is the Buenos Aires day of the workflow clock (time-skipped in this suite),
    # computed once and passed to both activities.
    date.fromisoformat(result.today)
    assert all(c[1].today == result.today and c[1].tenant_id == "t-1" for c in fake.calls)


async def test_release_only_run(env: WorkflowEnvironment) -> None:
    fake = FakePayments()
    result = await _run(env, PaymentRemindersInput("t-1", release_only=True), fake)
    assert [c[0] for c in fake.calls] == ["release"]
    assert result.queued is None and result.released == 1


# ── The activity against the seeded demo (Lakeshore's team enrollment) ─────────────────────


TENANT = fixture_id("igs", "tenant", "igs")
DB = "igs_test_c5_payments"


@pytest.fixture(scope="module")
def db_url() -> str:
    try:
        prepare_database(DB)
    except DatabaseUnavailableError as exc:  # pragma: no cover - env dependent
        pytest.skip(f"Postgres not available: {exc}")
    return database_url(DB, driver="postgresql+asyncpg")


@pytest.fixture
async def engine(db_url: str) -> AsyncIterator[AsyncEngine]:
    eng = create_engine(db_url, poolclass=NullPool)
    async with system_scope(engine=eng) as s:
        await load(s)
    yield eng
    await eng.dispose()


async def test_activity_queues_lakeshore_once(engine: AsyncEngine) -> None:
    llm = FakeLLM(
        [
            Scripted(
                json={
                    "subject": "IGS-2711: enrollment for Buenos Aires",
                    "body": f"Hi Dana, a quick note before your budget meeting.\n\n{DETAILS}\n\n"
                    "— Martín, Infinity Global Sports",
                }
            )
        ]
    )
    acts = PaymentActivities(engine=engine, llm=llm)
    run = PaymentRunInput(str(TENANT), "2026-10-22")
    first = await acts.queue_reminders(run)
    assert (first.reminders, first.approvals_created, first.template_fallbacks) == (1, 1, 0)
    again = await acts.queue_reminders(run)  # a retried / re-run day: nothing new
    assert again.approvals_created == 0
    async with system_scope(engine=engine) as s:
        (approval,) = (
            await s.scalars(
                select(Approval).where(
                    Approval.proposed_action["action"].astext == "send_payment_reminder"
                )
            )
        ).all()
    params = approval.proposed_action["params"]
    assert params["to"]["name"] == "Dana Whitfield"
    assert "24 travelers × US$95" in params["body"] and "US$2,280" in params["body"]
    assert approval.details["draft"]["source"] == "llm"
    assert "Recordatorio de pago a Dana Whitfield · IGS-2711 · US$2.280" in approval.title
    assert await acts.release_approved(run) == 0  # pending: nothing leaves


def test_schedules_target_this_workflow() -> None:
    from temporalio.workflow import _Definition

    from igs_common.payments.temporal import WORKFLOW_TYPE

    defn = _Definition.must_from_class(PaymentRemindersWorkflow)
    assert defn.name == WORKFLOW_TYPE
