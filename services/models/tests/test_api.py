"""HTTP contract tests with fake models: fast, no weights needed."""

from __future__ import annotations

import httpx
import pytest

from igs_models.app import create_app
from igs_models.encoders import Embeddings
from igs_models.settings import Settings


class FakeEmbedder:
    dim = 4

    def __init__(self) -> None:
        self.batches: list[int] = []

    def encode(self, texts: list[str]) -> Embeddings:
        self.batches.append(len(texts))
        return Embeddings(
            dense=[[float(len(t)), 0.0, 0.0, 1.0] for t in texts],
            sparse=[{"7": 0.5} for _ in texts],
        )


class FakeScorer:
    def score(self, query: str, documents: list[str]) -> list[float]:
        return [1.0 if query in d else 0.1 for d in documents]


@pytest.fixture
def fakes() -> tuple[FakeEmbedder, FakeScorer]:
    return FakeEmbedder(), FakeScorer()


@pytest.fixture
async def client(fakes: tuple[FakeEmbedder, FakeScorer]):
    settings = Settings(batch_size=2, max_texts_per_request=5, max_chars_per_text=20)
    app = create_app(settings, loader=lambda _s: fakes)
    async with app.router.lifespan_context(app):
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://t") as c:
            yield c


async def test_healthz(client: httpx.AsyncClient) -> None:
    r = await client.get("/healthz")
    assert r.json() == {"status": "ok"}


async def test_embed_batches_and_keeps_order(
    client: httpx.AsyncClient, fakes: tuple[FakeEmbedder, FakeScorer]
) -> None:
    r = await client.post("/embed", json={"texts": ["a", "bb", "ccc", "dddd", "e"]})
    assert r.status_code == 200
    body = r.json()
    assert body["dim"] == 4
    assert [v[0] for v in body["dense"]] == [1.0, 2.0, 3.0, 4.0, 1.0]
    assert body["sparse"] == [{"7": 0.5}] * 5
    assert fakes[0].batches == [2, 2, 1]


async def test_embed_limits(client: httpx.AsyncClient) -> None:
    too_many = await client.post("/embed", json={"texts": ["x"] * 6})
    assert too_many.status_code == 413
    too_long = await client.post("/embed", json={"texts": ["x" * 21]})
    assert too_long.status_code == 413
    empty = await client.post("/embed", json={"texts": []})
    assert empty.status_code == 422


async def test_rerank_sorts_and_truncates(client: httpx.AsyncClient) -> None:
    r = await client.post(
        "/rerank",
        json={"query": "visa", "documents": ["tango", "visa info", "asado", "visa"], "top_n": 2},
    )
    assert r.status_code == 200
    assert [x["index"] for x in r.json()["results"]] == [1, 3]
