"""Worker bootstrap: one process polls the ``flows`` and ``ingestion`` task queues.

In GKE each queue gets its own Deployment (scaled by KEDA on queue backlog); locally one
process runs both. ``python -m igs_worker`` or ``python -m igs_worker --queue flows``.
"""

import argparse
import asyncio
import logging
import os
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from typing import Any

from temporalio.client import Client
from temporalio.converter import DataConverter
from temporalio.worker import Worker

from igs_common.temporal import connect_client, make_data_converter

from .activities.conversation import ConversationActivities, InMemoryMessages, OutboxMessageSink
from .activities.nodes import NodeActivities
from .activities.payments import PaymentActivities
from .activities.records import RecordActivities
from .activities.records_sql import SqlApprovals, SqlFlowVersions, SqlNodeRunSink
from .agent_runner import AgentRunner
from .agent_tools import default_registry
from .domain_actions import SqlDomainActions
from .retrieval import RagRetriever
from .settings import WorkerSettings
from .telemetry import tracing_interceptors
from .workflows.flow_execution import FlowExecutionWorkflow
from .workflows.ingestion import INGESTION_ACTIVITIES, INGESTION_WORKFLOWS
from .workflows.payments import PAYMENT_WORKFLOWS

log = logging.getLogger("igs_worker")


@dataclass
class FlowActivities:
    nodes: NodeActivities
    conversation: ConversationActivities
    records: RecordActivities
    payments: PaymentActivities | None = None

    def all(self) -> list[Callable[..., Any]]:
        acts = [*self.nodes.all(), *self.conversation.all(), *self.records.all()]
        return acts + (self.payments.all() if self.payments else [])


def build_flow_activities(settings: WorkerSettings) -> FlowActivities:
    """Production wiring: Postgres domain actions + outbox, OpenAI, RAG retrieval."""
    from igs_common.db.session import configure
    from igs_common.llm import create_llm

    engine = configure(settings.database_url) if settings.database_url else None
    llm = create_llm() if os.environ.get("OPENAI_API_KEY") else None
    actions = SqlDomainActions(engine) if engine is not None else None
    retriever = RagRetriever()
    messages = OutboxMessageSink(engine) if engine is not None else InMemoryMessages()
    agent = (
        AgentRunner(llm, default_registry(actions, retriever))
        if llm is not None and actions is not None
        else None
    )
    if llm is None:
        log.warning("OPENAI_API_KEY not set: agent, extract and classify nodes will fail")
    return FlowActivities(
        nodes=NodeActivities(
            max_inline_bytes=settings.inline_output_max_bytes,
            actions=actions,
            agent=agent,
            retriever=retriever,
            llm=llm,
            messages=messages,
        ),
        conversation=ConversationActivities(messages=messages, llm=llm),
        # Without a database (tests, dry runs) records stay in memory.
        records=(
            RecordActivities(
                sink=SqlNodeRunSink(engine),
                approvals=SqlApprovals(engine),
                versions=SqlFlowVersions(engine),
            )
            if engine is not None
            else RecordActivities()
        ),
        payments=PaymentActivities(engine=engine, llm=llm) if engine is not None else None,
    )


def data_converter(settings: WorkerSettings) -> DataConverter:
    return make_data_converter(
        settings.codec_key, codec_key_id=settings.codec_key_id, environment=settings.environment
    )


async def connect(settings: WorkerSettings) -> Client:
    return await connect_client(
        settings.temporal_address,
        namespace=settings.temporal_namespace,
        data_converter=data_converter(settings),
        interceptors=tracing_interceptors(settings),
    )


def build_workers(
    client: Client,
    settings: WorkerSettings,
    queues: Sequence[str],
    flow_activities: FlowActivities | None = None,
) -> list[Worker]:
    workers: list[Worker] = []
    if settings.task_queue_flows in queues:
        acts = flow_activities or build_flow_activities(settings)
        workers.append(
            Worker(
                client,
                task_queue=settings.task_queue_flows,
                workflows=[FlowExecutionWorkflow, *PAYMENT_WORKFLOWS],
                activities=acts.all(),
            )
        )
    if settings.task_queue_ingestion in queues:
        workers.append(
            Worker(
                client,
                task_queue=settings.task_queue_ingestion,
                workflows=INGESTION_WORKFLOWS,
                activities=INGESTION_ACTIVITIES,
            )
        )
    return workers


async def main(argv: Sequence[str] | None = None) -> None:
    settings = WorkerSettings()
    parser = argparse.ArgumentParser(prog="igs_worker")
    parser.add_argument(
        "--queue",
        action="append",
        choices=[settings.task_queue_flows, settings.task_queue_ingestion],
        help="task queue to poll (repeatable); default: all",
    )
    args = parser.parse_args(argv)
    queues = args.queue or [settings.task_queue_flows, settings.task_queue_ingestion]
    logging.basicConfig(level=logging.INFO)
    client = await connect(settings)
    workers = build_workers(client, settings, queues)
    log.info("polling %s on %s", queues, settings.temporal_address)
    await asyncio.gather(*(w.run() for w in workers))
