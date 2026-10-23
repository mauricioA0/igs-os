"""Pinned model sources and the on-disk layout the service loads from.

The service only ever reads `*.safetensors` from `IGS_MODELS_DIR`. Upstream BGE-M3 ships
pickled weights (`pytorch_model.bin`, `sparse_linear.pt`), so `scripts/prepare_models.py`
downloads the pinned revision, verifies checksums, converts with `torch.load(weights_only=True)`
(restricted unpickler, no code execution) and writes safetensors plus a `manifest.json`.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class ModelSource:
    name: str
    repo_id: str
    # Full commit sha: a tag or branch could move under us.
    revision: str
    # Upstream files that are copied as-is (tokenizer + config).
    plain_files: tuple[str, ...]
    # Upstream weight file -> safetensors file written locally.
    weights: dict[str, str]
    # sha256 of each upstream weight file at `revision`; a mismatch aborts preparation.
    expected_sha256: dict[str, str]


TOKENIZER_FILES = (
    "config.json",
    "tokenizer.json",
    "tokenizer_config.json",
    "special_tokens_map.json",
    "sentencepiece.bpe.model",
)

BGE_M3 = ModelSource(
    name="bge-m3",
    repo_id="BAAI/bge-m3",
    revision="5617a9f61b028005a4858fdac845db406aefb181",
    plain_files=TOKENIZER_FILES,
    weights={
        "pytorch_model.bin": "model.safetensors",
        "sparse_linear.pt": "sparse_linear.safetensors",
    },
    expected_sha256={
        "pytorch_model.bin": "b5e0ce3470abf5ef3831aa1bd5553b486803e83251590ab7ff35a117cf6aad38",
        "sparse_linear.pt": "45c93804d2142b8f6d7ec6914ae23a1eee9c6a1d27d83d908a20d2afb3595ad9",
    },
)

BGE_RERANKER = ModelSource(
    name="bge-reranker-v2-m3",
    repo_id="BAAI/bge-reranker-v2-m3",
    revision="953dc6f6f85a1b2dbfca4c34a2796e7dde08d41e",
    plain_files=TOKENIZER_FILES,
    # Already published as safetensors upstream: copied and checksummed, not converted.
    weights={"model.safetensors": "model.safetensors"},
    expected_sha256={
        "model.safetensors": "d9e3e081faff1eefb84019509b2f5558fd74c1a05a2c7db22f74174fcedb5286",
    },
)

SOURCES = (BGE_M3, BGE_RERANKER)
