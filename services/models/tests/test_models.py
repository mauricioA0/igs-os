"""Real-weight tests. Slow (load ~2 GB each); skipped unless `models/` was prepared.

Run: uv run pytest -m slow
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from igs_models.encoders import BGEM3, ModelIntegrityError, Reranker, _verify

MODELS = Path(__file__).resolve().parents[1] / "models"
GOLDEN = json.loads((Path(__file__).parent / "fixtures" / "bge_m3_golden.json").read_text())

pytestmark = [
    pytest.mark.slow,
    pytest.mark.skipif(not (MODELS / "bge-m3" / "manifest.json").exists(), reason="no models/"),
]


@pytest.fixture(scope="module")
def bge() -> BGEM3:
    return BGEM3(MODELS / "bge-m3", max_length=512)


def test_matches_flagembedding_golden(bge: BGEM3) -> None:
    out = bge.encode(GOLDEN["texts"])
    for got, want in zip(out.dense, GOLDEN["dense_head"], strict=True):
        assert len(got) == 1024
        assert got[:16] == pytest.approx(want, abs=1e-5)
    for got, want in zip(out.sparse, GOLDEN["sparse"], strict=True):
        assert set(got) == set(want)
        assert [got[k] for k in want] == pytest.approx(list(want.values()), abs=1e-5)


def test_cross_lingual_similarity(bge: BGEM3) -> None:
    out = bge.encode(
        ["Which providers still need to confirm?", "¿Qué proveedores faltan confirmar?", "Tango"]
    )
    en, es, tango = out.dense

    def dot(a: list[float], b: list[float]) -> float:
        return sum(x * y for x, y in zip(a, b, strict=True))

    assert dot(en, es) > dot(en, tango) + 0.2


def test_reranker_orders_relevant_first() -> None:
    r = Reranker(MODELS / "bge-reranker-v2-m3", max_length=512)
    scores = r.score(
        "Do US citizens need a visa for Brazil?",
        ["Tango class and asado night.", "US citizens need an e-visa to enter Brazil."],
    )
    assert scores[1] > 0.5 > scores[0]


def test_tampered_file_is_rejected(tmp_path: Path) -> None:
    src = MODELS / "bge-m3"
    dst = tmp_path / "bge-m3"
    dst.mkdir()
    for f in src.iterdir():
        (dst / f.name).symlink_to(f)
    (dst / "config.json").unlink()
    (dst / "config.json").write_text("{}")
    with pytest.raises(ModelIntegrityError):
        _verify(dst)
