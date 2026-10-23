import json
from collections.abc import AsyncIterator
from pathlib import Path
from typing import Any

import pytest
from temporalio import activity
from temporalio.testing import WorkflowEnvironment

from igs_worker.activities.types import NodeOutcome, NodeTask
from igs_worker.domain_actions import ActionContext

REPO = Path(__file__).resolve().parents[3]
EXAMPLES = REPO / "packages" / "flow-schema" / "examples"


@pytest.fixture(scope="session")
async def env() -> AsyncIterator[WorkflowEnvironment]:
    async with await WorkflowEnvironment.start_time_skipping() as env:
        yield env


def example(name: str) -> dict[str, Any]:
    return json.loads((EXAMPLES / f"{name}.json").read_text())


def doc(
    nodes: list[dict[str, Any]],
    edges: list[tuple],
    *,
    entry: str | None = None,
    flow_id: str = "test-flow",
    settings: dict[str, Any] | None = None,
    trigger: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """A schema-valid flow document from compact node/edge lists."""
    return {
        "schemaVersion": "1",
        "id": flow_id,
        "name": flow_id,
        "trigger": trigger or {"type": "manual"},
        "entry": entry or nodes[0]["id"],
        "nodes": nodes,
        "edges": [
            {"from": e[0], "to": e[-1], **({"port": e[1]} if len(e) == 3 else {})} for e in edges
        ],
        "settings": settings or {},
    }


class FakeDomain:
    """Stands in for node.action / node.io with canned domain responses."""

    def __init__(self, responses: dict[str, Any] | None = None) -> None:
        self.responses = responses or {}
        self.calls: list[NodeTask] = []

    @activity.defn(name="node.action")
    async def action(self, task: NodeTask) -> NodeOutcome:
        self.calls.append(task)
        resp = self.responses.get(task.config["action"], {"ok": True})
        if isinstance(resp, Exception):
            raise resp
        return NodeOutcome(port="next", output=resp)

    @activity.defn(name="node.io")
    async def io(self, task: NodeTask) -> NodeOutcome:
        self.calls.append(task)
        resp = self.responses.get(task.node_type, {"ok": True})
        if isinstance(resp, Exception):
            raise resp
        return NodeOutcome(port="next", output=resp)

    def all(self) -> list[Any]:
        return [self.action, self.io]


class FakeActions:
    """``DomainActions`` for agent tools: canned results per action, records every call."""

    def __init__(self, responses: dict[str, Any] | None = None) -> None:
        self.responses = responses or {}
        self.calls: list[tuple[str, dict[str, Any], ActionContext]] = []

    async def run(self, action: str, inputs: dict[str, Any], ctx: ActionContext) -> Any:
        self.calls.append((action, inputs, ctx))
        resp = self.responses.get(action, {"ok": True})
        if isinstance(resp, Exception):
            raise resp
        return resp
