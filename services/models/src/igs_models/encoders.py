"""BGE-M3 (dense + sparse) and bge-reranker-v2-m3, loaded from safetensors only.

BGE-M3 is reimplemented on top of `transformers` instead of FlagEmbedding so that loading never
touches pickled files: dense = L2-normalized CLS vector of the last hidden state; sparse =
ReLU(sparse_linear(hidden)) per token, max-pooled per token id, special tokens dropped. Same math
as FlagEmbedding's `BGEM3FlagModel` (verified against it in tests/test_parity.py).
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from hashlib import sha256
from pathlib import Path

import torch
from safetensors.torch import load_file
from transformers import (
    AutoModel,
    AutoModelForSequenceClassification,
    AutoTokenizer,
    PreTrainedTokenizerBase,
)


class ModelIntegrityError(RuntimeError):
    pass


def _verify(model_dir: Path) -> None:
    """Refuse to start if any shipped file differs from the manifest written at build time."""
    manifest = json.loads((model_dir / "manifest.json").read_text())
    for name, expected in manifest["files_sha256"].items():
        h = sha256()
        with (model_dir / name).open("rb") as f:
            for block in iter(lambda: f.read(1 << 20), b""):
                h.update(block)
        if h.hexdigest() != expected:
            raise ModelIntegrityError(f"{model_dir.name}/{name}: checksum mismatch")
    if any(model_dir.glob("*.bin")) or any(model_dir.glob("*.pt")):
        raise ModelIntegrityError(f"{model_dir.name}: pickled weights present; safetensors only")


@dataclass(frozen=True)
class Embeddings:
    dense: list[list[float]]
    # token id (as str, JSON keys) -> weight
    sparse: list[dict[str, float]]


class BGEM3:
    def __init__(self, model_dir: Path, *, max_length: int, device: str = "cpu") -> None:
        _verify(model_dir)
        self.max_length = max_length
        self.device = torch.device(device)
        self.tokenizer: PreTrainedTokenizerBase = AutoTokenizer.from_pretrained(model_dir)
        self.model = AutoModel.from_pretrained(
            model_dir, use_safetensors=True, dtype=torch.float32
        ).to(self.device)
        self.model.eval()
        sparse_state = load_file(str(model_dir / "sparse_linear.safetensors"))
        hidden = self.model.config.hidden_size
        self.sparse_linear = torch.nn.Linear(hidden, 1).to(self.device)
        self.sparse_linear.load_state_dict(sparse_state)
        self.sparse_linear.eval()
        self._skip_ids = {
            tid
            for tid in (
                self.tokenizer.cls_token_id,
                self.tokenizer.eos_token_id,
                self.tokenizer.pad_token_id,
                self.tokenizer.unk_token_id,
            )
            if tid is not None
        }

    @property
    def dim(self) -> int:
        return int(self.model.config.hidden_size)

    @torch.inference_mode()
    def encode(self, texts: list[str]) -> Embeddings:
        batch = self.tokenizer(
            texts,
            padding=True,
            truncation=True,
            max_length=self.max_length,
            return_tensors="pt",
        ).to(self.device)
        hidden = self.model(**batch).last_hidden_state
        dense = torch.nn.functional.normalize(hidden[:, 0], dim=-1)
        weights = torch.relu(self.sparse_linear(hidden)).squeeze(-1)
        weights = weights * batch["attention_mask"]
        sparse: list[dict[str, float]] = []
        ids = batch["input_ids"].tolist()
        for row_ids, row_w in zip(ids, weights.tolist(), strict=True):
            out: dict[str, float] = {}
            for tid, w in zip(row_ids, row_w, strict=True):
                if tid in self._skip_ids or w <= 0:
                    continue
                key = str(tid)
                if w > out.get(key, 0.0):
                    out[key] = w
            sparse.append(out)
        return Embeddings(dense=dense.tolist(), sparse=sparse)


class Reranker:
    def __init__(self, model_dir: Path, *, max_length: int, device: str = "cpu") -> None:
        _verify(model_dir)
        self.max_length = max_length
        self.device = torch.device(device)
        self.tokenizer: PreTrainedTokenizerBase = AutoTokenizer.from_pretrained(model_dir)
        self.model = AutoModelForSequenceClassification.from_pretrained(
            model_dir, use_safetensors=True, dtype=torch.float32
        ).to(self.device)
        self.model.eval()

    @torch.inference_mode()
    def score(self, query: str, documents: list[str]) -> list[float]:
        """Relevance in [0, 1] (sigmoid of the raw logit) for each document, input order."""
        batch = self.tokenizer(
            [[query, d] for d in documents],
            padding=True,
            truncation=True,
            max_length=self.max_length,
            return_tensors="pt",
        ).to(self.device)
        logits = self.model(**batch).logits.view(-1).float()
        return torch.sigmoid(logits).tolist()
