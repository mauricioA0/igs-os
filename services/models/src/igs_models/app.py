"""HTTP surface of the models service: /embed, /rerank, /healthz.

Models are loaded once in the lifespan. Inference is CPU/GPU-bound and synchronous, so it runs in
a single worker thread (serialized): concurrent requests queue instead of oversubscribing cores.
"""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator, Callable
from concurrent.futures import ThreadPoolExecutor
from contextlib import asynccontextmanager
from typing import Annotated, Literal, Protocol

import torch
from fastapi import FastAPI, HTTPException, Request
from pydantic import BaseModel, Field

from igs_models.encoders import BGEM3, Embeddings, Reranker
from igs_models.settings import Settings


class Embedder(Protocol):
    @property
    def dim(self) -> int: ...
    def encode(self, texts: list[str]) -> Embeddings: ...


class Scorer(Protocol):
    def score(self, query: str, documents: list[str]) -> list[float]: ...


class EmbedRequest(BaseModel):
    texts: Annotated[list[str], Field(min_length=1)]
    # Kept for API symmetry with other embedders. BGE-M3 uses no query/passage prefixes.
    kind: Literal["query", "passage"] = "passage"


class EmbedResponse(BaseModel):
    model: str
    dim: int
    dense: list[list[float]]
    sparse: list[dict[str, float]]


class RerankRequest(BaseModel):
    query: Annotated[str, Field(min_length=1)]
    documents: Annotated[list[str], Field(min_length=1)]
    top_n: Annotated[int | None, Field(ge=1)] = None


class RerankResult(BaseModel):
    index: int
    score: float


class RerankResponse(BaseModel):
    model: str
    results: list[RerankResult]


EMBED_MODEL = "BAAI/bge-m3"
RERANK_MODEL = "BAAI/bge-reranker-v2-m3"


def create_app(
    settings: Settings | None = None,
    *,
    loader: Callable[[Settings], tuple[Embedder, Scorer]] | None = None,
) -> FastAPI:
    settings = settings or Settings()

    def default_loader(s: Settings) -> tuple[Embedder, Scorer]:
        if s.threads:
            torch.set_num_threads(s.threads)
        embedder = BGEM3(s.dir / "bge-m3", max_length=s.embed_max_tokens, device=s.device)
        reranker = Reranker(
            s.dir / "bge-reranker-v2-m3", max_length=s.rerank_max_tokens, device=s.device
        )
        return embedder, reranker

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="inference")
        embedder, reranker = await asyncio.get_running_loop().run_in_executor(
            executor, loader or default_loader, settings
        )
        app.state.embedder = embedder
        app.state.reranker = reranker
        app.state.executor = executor
        try:
            yield
        finally:
            executor.shutdown(wait=False, cancel_futures=True)

    app = FastAPI(title="igs-models", version="0.1.0", lifespan=lifespan)

    async def run(request: Request, fn: Callable[[], object]) -> object:
        return await asyncio.get_running_loop().run_in_executor(request.app.state.executor, fn)

    def check_texts(texts: list[str], limit: int, what: str) -> None:
        if len(texts) > limit:
            raise HTTPException(413, f"too many {what}: {len(texts)} > {limit}")
        for i, t in enumerate(texts):
            if len(t) > settings.max_chars_per_text:
                raise HTTPException(
                    413, f"{what}[{i}] has {len(t)} chars > {settings.max_chars_per_text}"
                )

    @app.get("/healthz")
    async def healthz(request: Request) -> dict[str, str]:
        ready = hasattr(request.app.state, "embedder")
        return {"status": "ok" if ready else "loading"}

    @app.post("/embed")
    async def embed(body: EmbedRequest, request: Request) -> EmbedResponse:
        check_texts(body.texts, settings.max_texts_per_request, "texts")
        embedder: Embedder = request.app.state.embedder
        size = settings.batch_size

        def work() -> Embeddings:
            dense: list[list[float]] = []
            sparse: list[dict[str, float]] = []
            for i in range(0, len(body.texts), size):
                part = embedder.encode(body.texts[i : i + size])
                dense.extend(part.dense)
                sparse.extend(part.sparse)
            return Embeddings(dense=dense, sparse=sparse)

        out = await run(request, work)
        assert isinstance(out, Embeddings)
        return EmbedResponse(
            model=EMBED_MODEL, dim=embedder.dim, dense=out.dense, sparse=out.sparse
        )

    @app.post("/rerank")
    async def rerank(body: RerankRequest, request: Request) -> RerankResponse:
        check_texts(body.documents, settings.max_documents_per_rerank, "documents")
        check_texts([body.query], 1, "query")
        reranker: Scorer = request.app.state.reranker
        size = settings.batch_size

        def work() -> list[float]:
            scores: list[float] = []
            for i in range(0, len(body.documents), size):
                scores.extend(reranker.score(body.query, body.documents[i : i + size]))
            return scores

        scores = await run(request, work)
        assert isinstance(scores, list)
        ranked = sorted(enumerate(scores), key=lambda p: (-p[1], p[0]))
        if body.top_n is not None:
            ranked = ranked[: body.top_n]
        return RerankResponse(
            model=RERANK_MODEL,
            results=[RerankResult(index=i, score=s) for i, s in ranked],
        )

    return app
