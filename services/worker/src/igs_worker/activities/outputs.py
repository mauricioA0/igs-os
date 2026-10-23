"""Where node outputs live when they're too big for Temporal history."""

import json
from typing import Any, Protocol

from .types import OutputRef


class OutputStore(Protocol):
    async def put(self, execution_id: str, node_id: str, iteration: int, data: bytes) -> str: ...

    async def get(self, uri: str) -> bytes: ...


class InMemoryOutputStore:
    """Tests and local dev."""

    def __init__(self) -> None:
        self.objects: dict[str, bytes] = {}

    async def put(self, execution_id: str, node_id: str, iteration: int, data: bytes) -> str:
        uri = f"mem://{execution_id}/{node_id}/{iteration}"
        self.objects[uri] = data
        return uri

    async def get(self, uri: str) -> bytes:
        return self.objects[uri]


class GcsOutputStore:
    """``gs://<bucket>/executions/<execution>/<node>/<iteration>.json`` — wired in phase 4."""

    def __init__(self, bucket: str) -> None:
        self.bucket = bucket

    async def put(self, execution_id: str, node_id: str, iteration: int, data: bytes) -> str:
        raise NotImplementedError("GCS output store lands with the phase 4 infra")

    async def get(self, uri: str) -> bytes:
        raise NotImplementedError("GCS output store lands with the phase 4 infra")


async def inline_or_store(
    store: OutputStore,
    execution_id: str,
    node_id: str,
    iteration: int,
    output: Any,
    max_inline_bytes: int,
) -> tuple[Any, OutputRef | None]:
    """Small outputs travel inline; big ones go to the store and only a reference goes back."""
    data = json.dumps(output, separators=(",", ":"), default=str).encode()
    if len(data) <= max_inline_bytes:
        return output, None
    uri = await store.put(execution_id, node_id, iteration, data)
    return None, OutputRef(
        uri=uri, size_bytes=len(data), preview=data[:200].decode(errors="ignore")
    )
