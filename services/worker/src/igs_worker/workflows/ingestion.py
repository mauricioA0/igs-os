"""RAG ingestion workflows (task queue ``ingestion``).

``IngestDocument``: prepare (parse → chunk → quarantine check → chunk rows, clearing the store
if the content changed) → embed + upsert in batches, a few in parallel → finish. Re-running is
safe: unchanged documents are skipped by content hash and every write is keyed by
content-addressed ids.

``IndexInteractions``: pages through a tenant's interactions (optionally one account) and indexes
them for Account 360. Continues-as-new every few pages so history stays small for big tenants.

Only ids cross the workflow boundary; chunk text never enters Temporal history.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from datetime import timedelta

from temporalio import workflow
from temporalio.client import Client
from temporalio.common import RetryPolicy, WorkflowIDReusePolicy
from temporalio.exceptions import ActivityError

with workflow.unsafe.imports_passed_through():
    from ..activities.ingestion import (
        FailDocumentInput,
        FinishDocumentInput,
        IndexBatchInput,
        IndexBatchResult,
        IngestionActivities,
        ListInteractionsInput,
        PrepareDocumentInput,
        PreparedRefs,
        PrepareInteractionsInput,
    )

EMBED_BATCH = 64
MAX_PARALLEL_BATCHES = 4
INTERACTION_PAGE = 100
PAGES_PER_RUN = 20

_RETRY = RetryPolicy(
    initial_interval=timedelta(seconds=2),
    maximum_interval=timedelta(minutes=2),
    maximum_attempts=6,
    non_retryable_error_types=["validation"],
)
_SHORT = timedelta(minutes=2)
_LONG = timedelta(minutes=10)


@dataclass
class IngestDocumentInput:
    tenant_id: str
    document_id: str
    force: bool = False


@dataclass
class IngestResult:
    document_id: str
    chunks: int = 0
    indexed: int = 0
    quarantined: int = 0
    skipped: bool = False


@dataclass
class IndexInteractionsInput:
    tenant_id: str
    account_id: str | None = None
    force: bool = False
    page_size: int = INTERACTION_PAGE
    pages_per_run: int = PAGES_PER_RUN
    # Carried across continue-as-new:
    after: str | None = None
    interactions: int = 0
    chunks: int = 0
    indexed: int = 0
    quarantined: int = 0


@dataclass
class IndexInteractionsResult:
    interactions: int
    chunks: int
    indexed: int
    quarantined: int


async def _index(tenant_id: str, chunk_ids: list[str]) -> tuple[int, str | None]:
    """Embed + upsert in batches, at most ``MAX_PARALLEL_BATCHES`` activities at a time."""
    batches = [chunk_ids[i : i + EMBED_BATCH] for i in range(0, len(chunk_ids), EMBED_BATCH)]
    indexed = 0
    model: str | None = None
    for start in range(0, len(batches), MAX_PARALLEL_BATCHES):
        results: list[IndexBatchResult] = await asyncio.gather(
            *(
                workflow.execute_activity(
                    "ingest.index_batch",
                    IndexBatchInput(tenant_id=tenant_id, chunk_ids=batch),
                    result_type=IndexBatchResult,
                    start_to_close_timeout=_LONG,
                    retry_policy=_RETRY,
                )
                for batch in batches[start : start + MAX_PARALLEL_BATCHES]
            )
        )
        indexed += sum(r.indexed for r in results)
        model = model or next((r.embedding_model for r in results), None)
    return indexed, model


@workflow.defn(name="IngestDocument")
class IngestDocumentWorkflow:
    @workflow.run
    async def run(self, inp: IngestDocumentInput) -> IngestResult:
        prepared: PreparedRefs = await workflow.execute_activity(
            "ingest.prepare_document",
            PrepareDocumentInput(inp.tenant_id, inp.document_id, inp.force),
            result_type=PreparedRefs,
            start_to_close_timeout=_LONG,
            retry_policy=_RETRY,
        )
        if prepared.unchanged:
            return IngestResult(inp.document_id, chunks=prepared.chunks, skipped=True)
        try:
            indexed, model = await _index(inp.tenant_id, prepared.chunk_ids)
        except ActivityError as err:
            await workflow.execute_activity(
                "ingest.fail_document",
                FailDocumentInput(
                    inp.tenant_id, inp.document_id, prepared.job_id, str(err.cause or err)
                ),
                start_to_close_timeout=_SHORT,
                retry_policy=_RETRY,
            )
            raise
        await workflow.execute_activity(
            "ingest.finish_document",
            FinishDocumentInput(inp.tenant_id, inp.document_id, prepared.job_id, indexed, model),
            start_to_close_timeout=_SHORT,
            retry_policy=_RETRY,
        )
        return IngestResult(
            inp.document_id,
            chunks=prepared.chunks,
            indexed=indexed,
            quarantined=prepared.quarantined,
        )


@workflow.defn(name="IndexInteractions")
class IndexInteractionsWorkflow:
    @workflow.run
    async def run(self, inp: IndexInteractionsInput) -> IndexInteractionsResult:
        state = inp
        for _ in range(state.pages_per_run):
            ids: list[str] = await workflow.execute_activity(
                "ingest.list_interactions",
                ListInteractionsInput(
                    state.tenant_id, state.account_id, state.after, state.page_size
                ),
                result_type=list[str],
                start_to_close_timeout=_SHORT,
                retry_policy=_RETRY,
            )
            if not ids:
                break
            prepared: PreparedRefs = await workflow.execute_activity(
                "ingest.prepare_interactions",
                PrepareInteractionsInput(state.tenant_id, ids, state.force),
                result_type=PreparedRefs,
                start_to_close_timeout=_LONG,
                retry_policy=_RETRY,
            )
            indexed, _ = await _index(state.tenant_id, prepared.chunk_ids)
            state.after = ids[-1]
            state.interactions += prepared.sources
            state.chunks += prepared.chunks
            state.quarantined += prepared.quarantined
            state.indexed += indexed
            if len(ids) < state.page_size:
                break
        else:
            workflow.continue_as_new(state)
        return IndexInteractionsResult(
            state.interactions, state.chunks, state.indexed, state.quarantined
        )


INGESTION_WORKFLOWS = [IngestDocumentWorkflow, IndexInteractionsWorkflow]
# Default instance resolves DB / embedder / store lazily from the environment on first use.
INGESTION_ACTIVITIES = IngestionActivities().all()


async def start_index_interactions(
    client: Client,
    tenant_id: str,
    *,
    account_id: str | None = None,
    force: bool = False,
    task_queue: str = "ingestion",
) -> str:
    """Entry point for the seed / demo reset (via Temporal). Deterministic id per tenant/account,
    so a second call while a run is in flight fails fast instead of indexing twice."""
    handle = await client.start_workflow(
        IndexInteractionsWorkflow.run,
        IndexInteractionsInput(tenant_id=tenant_id, account_id=account_id, force=force),
        id=f"index-interactions-{tenant_id}-{account_id or 'all'}",
        task_queue=task_queue,
        id_reuse_policy=WorkflowIDReusePolicy.ALLOW_DUPLICATE,
    )
    return handle.id


async def start_ingest_document(
    client: Client,
    tenant_id: str,
    document_id: str,
    *,
    force: bool = False,
    task_queue: str = "ingestion",
) -> str:
    handle = await client.start_workflow(
        IngestDocumentWorkflow.run,
        IngestDocumentInput(tenant_id=tenant_id, document_id=document_id, force=force),
        id=f"ingest-document-{document_id}",
        task_queue=task_queue,
        id_reuse_policy=WorkflowIDReusePolicy.ALLOW_DUPLICATE,
    )
    return handle.id
