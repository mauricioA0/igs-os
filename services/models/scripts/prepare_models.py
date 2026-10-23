"""Download pinned model revisions and write a safetensors-only model directory.

Usage: uv run python scripts/prepare_models.py --out ./models

Runs at image build time (see Dockerfile) and locally once. Reuses the Hugging Face cache, so a
machine that already ran spikes/embeddings downloads nothing.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import shutil
from pathlib import Path

import torch
from huggingface_hub import hf_hub_download
from safetensors import safe_open
from safetensors.torch import save_file

from igs_models.manifest import SOURCES, ModelSource


def _sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for block in iter(lambda: f.read(1 << 20), b""):
            h.update(block)
    return h.hexdigest()


def _fetch(source: ModelSource, filename: str) -> Path:
    return Path(hf_hub_download(source.repo_id, filename, revision=source.revision))


def _convert(src: Path, dst: Path) -> None:
    if src.suffix == ".safetensors":
        # Already safe: copy, then open lazily to make sure the header parses before shipping.
        shutil.copyfile(src, dst)
        with safe_open(str(dst), framework="pt") as f:
            if not list(f.keys()):
                raise SystemExit(f"{src.name}: no tensors")
        return
    # weights_only=True uses torch's restricted unpickler: tensors and plain containers only.
    # mmap keeps the 2 GB checkpoint in the page cache instead of private memory, so the
    # conversion fits in small build VMs.
    state = torch.load(src, map_location="cpu", weights_only=True, mmap=True)
    # safetensors refuses tensors that share storage: copy only those, keep the rest mapped.
    seen: set[int] = set()
    out: dict[str, torch.Tensor] = {}
    for key, tensor in state.items():
        ptr = tensor.untyped_storage().data_ptr()
        shared = ptr in seen
        seen.add(ptr)
        out[key] = tensor.clone() if shared or not tensor.is_contiguous() else tensor
    save_file(out, str(dst))


def prepare(source: ModelSource, out_root: Path) -> dict[str, object]:
    out = out_root / source.name
    out.mkdir(parents=True, exist_ok=True)
    files: dict[str, str] = {}
    for name in source.plain_files:
        shutil.copyfile(_fetch(source, name), out / name)
        files[name] = _sha256(out / name)
    upstream: dict[str, str] = {}
    for src_name, dst_name in source.weights.items():
        src = _fetch(source, src_name)
        upstream[src_name] = _sha256(src)
        expected = source.expected_sha256[src_name]
        if upstream[src_name] != expected:
            raise SystemExit(
                f"{source.repo_id}@{source.revision}: {src_name} sha256 {upstream[src_name]}"
                f" != pinned {expected}"
            )
        _convert(src, out / dst_name)
        files[dst_name] = _sha256(out / dst_name)
    entry = {
        "repo_id": source.repo_id,
        "revision": source.revision,
        "upstream_sha256": upstream,
        "files_sha256": files,
    }
    (out / "manifest.json").write_text(json.dumps(entry, indent=2) + "\n")
    return entry


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", type=Path, default=Path("models"))
    args = parser.parse_args()
    for source in SOURCES:
        entry = prepare(source, args.out)
        print(f"{source.name}: {entry['revision'][:12]} -> {args.out / source.name}")


if __name__ == "__main__":
    main()
