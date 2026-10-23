"""Ingestion workflows with fake activities (no DB, no network): batching, bounded fan-out,
skip-if-unchanged, failure bookkeeping, paging + continue-as-new for interactions."""

import asyncio
import uuid
from dataclasses import dataclass, field

import pytest
from temporalio import activity
from temporalio.client import WorkflowFailureError
from temporalio.exceptions import ApplicationError
from temporalio.testing import WorkflowEnvironment
from temporalio.worker import Worker

from igs_worker.activities.ingestion import (
    FailDocumentInput,
    FinishDocumentInput,
    IndexBatchInput,
    IndexBatchResult,
    ListInteractionsInput,
    PrepareDocumentInput,
    PreparedRefs,
    PrepareInteractionsInput,
)
from igs_worker.workflows import ingestion
from igs_worker.workflows.ingestion import (
    IndexInteractionsInput,
    IndexInteractionsResult,
    IndexInteractionsWorkflow,
    IngestDocumentInput,
    IngestDocumentWorkflow,
    IngestResult,
)


@dataclass
class FakeIngestion:
    chunk_count: int = 150
    unchanged: bool = False
    fail_batch: bool = False
    interactions: list[str] = field(default_factory=list)
    batches: list[int] = field(default_factory=list)
    in_flight: int = 0
    max_in_flight: int = 0
    finished: list[FinishDocumentInput] = field(default_factory=list)
    failed: list[FailDocumentInput] = field(default_factory=list)
    pages: list[str | None] = field(default_factory=list)

    @activity.defn(name="ingest.prepare_document")
    async def prepare_document(self, inp: PrepareDocumentInput) -> PreparedRefs:
        if self.unchanged:
            return PreparedRefs(unchanged=True, chunks=self.chunk_count, sources=1)
        ids = [f"c{i}" for i in range(self.chunk_count)]
        return PreparedRefs(chunk_ids=ids, chunks=self.chunk_count, quarantined=2, job_id="job-1")

    @activity.defn(name="ingest.index_batch")
    async def index_batch(self, inp: IndexBatchInput) -> IndexBatchResult:
        self.in_flight += 1
        self.max_in_flight = max(self.max_in_flight, self.in_flight)
        try:
            await asyncio.sleep(0.01)
            if self.fail_batch:
                raise ApplicationError("models service down", type="validation", non_retryable=True)
            self.batches.append(len(inp.chunk_ids))
            return IndexBatchResult(indexed=len(inp.chunk_ids), embedding_model="bge-m3")
        finally:
            self.in_flight -= 1

    @activity.defn(name="ingest.finish_document")
    async def finish_document(self, inp: FinishDocumentInput) -> None:
        self.finished.append(inp)

    @activity.defn(name="ingest.fail_document")
    async def fail_document(self, inp: FailDocumentInput) -> None:
        self.failed.append(inp)

    @activity.defn(name="ingest.list_interactions")
    async def list_interactions(self, inp: ListInteractionsInput) -> list[str]:
        self.pages.append(inp.after)
        start = self.interactions.index(inp.after) + 1 if inp.after else 0
        return self.interactions[start : start + inp.limit]

    @activity.defn(name="ingest.prepare_interactions")
    async def prepare_interactions(self, inp: PrepareInteractionsInput) -> PreparedRefs:
        ids = [f"{i}-chunk" for i in inp.interaction_ids]
        return PreparedRefs(chunk_ids=ids, sources=len(ids), chunks=len(ids))

    def all(self) -> list:
        return [
            self.prepare_document,
            self.index_batch,
            self.finish_document,
            self.fail_document,
            self.list_interactions,
            self.prepare_interactions,
        ]


async def _run(env: WorkflowEnvironment, fake: FakeIngestion, wf, arg, result_type):  # noqa: ANN001, ANN202
    queue = f"ingestion-{uuid.uuid4()}"
    async with Worker(
        env.client,
        task_queue=queue,
        workflows=ingestion.INGESTION_WORKFLOWS,
        activities=fake.all(),
    ):
        return await env.client.execute_workflow(
            wf, arg, id=f"wf-{uuid.uuid4()}", task_queue=queue, result_type=result_type
        )


async def test_document_is_indexed_in_bounded_parallel_batches(env: WorkflowEnvironment) -> None:
    fake = FakeIngestion(chunk_count=600)  # 10 batches of <=64
    result = await _run(
        env, fake, IngestDocumentWorkflow.run, IngestDocumentInput("t1", "d1"), IngestResult
    )
    assert result == IngestResult("d1", chunks=600, indexed=600, quarantined=2)
    assert sum(fake.batches) == 600 and max(fake.batches) == ingestion.EMBED_BATCH
    assert len(fake.batches) == 10
    assert 1 < fake.max_in_flight <= ingestion.MAX_PARALLEL_BATCHES
    assert fake.finished == [FinishDocumentInput("t1", "d1", "job-1", 600, "bge-m3")]


async def test_unchanged_document_is_skipped(env: WorkflowEnvironment) -> None:
    fake = FakeIngestion(unchanged=True)
    result = await _run(
        env, fake, IngestDocumentWorkflow.run, IngestDocumentInput("t1", "d1"), IngestResult
    )
    assert result.skipped and fake.batches == [] and fake.finished == []


async def test_failed_indexing_marks_document_failed(env: WorkflowEnvironment) -> None:
    fake = FakeIngestion(chunk_count=10, fail_batch=True)
    with pytest.raises(WorkflowFailureError):
        await _run(
            env, fake, IngestDocumentWorkflow.run, IngestDocumentInput("t1", "d1"), IngestResult
        )
    assert len(fake.failed) == 1 and fake.failed[0].job_id == "job-1"
    assert "models service down" in fake.failed[0].error
    assert fake.finished == []


async def test_interactions_page_through_and_continue_as_new(env: WorkflowEnvironment) -> None:
    fake = FakeIngestion(interactions=[f"i{n:03d}" for n in range(45)])
    result = await _run(
        env,
        fake,
        IndexInteractionsWorkflow.run,
        IndexInteractionsInput("t1", page_size=10, pages_per_run=2),
        IndexInteractionsResult,
    )
    assert result == IndexInteractionsResult(interactions=45, chunks=45, indexed=45, quarantined=0)
    # 5 pages (10,10 | 10,10 | 5) across three runs: continue-as-new carried the cursor.
    assert fake.pages == [None, "i009", "i019", "i029", "i039"]
