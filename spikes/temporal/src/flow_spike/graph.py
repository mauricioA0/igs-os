"""Tiny flow graph model: the shape a published flow version has when it reaches the worker."""

from dataclasses import dataclass, field
from typing import Any


@dataclass
class Node:
    id: str
    type: str  # "action" | "approval" | "end"
    params: dict[str, Any] = field(default_factory=dict)


@dataclass
class Edge:
    source: str
    target: str
    # Outcome of the source node that takes this edge; None = unconditional.
    when: str | None = None


@dataclass
class FlowGraph:
    flow_id: str
    version: int
    start: str
    nodes: list[Node]
    edges: list[Edge]

    def node(self, node_id: str) -> Node:
        for n in self.nodes:
            if n.id == node_id:
                return n
        raise KeyError(node_id)

    def next_node(self, node_id: str, outcome: str | None) -> str | None:
        for e in self.edges:
            if e.source == node_id and (e.when is None or e.when == outcome):
                return e.target
        return None


def proposal_approval_flow() -> FlowGraph:
    """draft_proposal → ops approval (signal, 48h timeout) → send_proposal | end."""
    return FlowGraph(
        flow_id="inbound-inquiry",
        version=3,
        start="draft",
        nodes=[
            Node("draft", "action", {"action": "draft_proposal"}),
            Node("approval", "approval", {"timeout_hours": 48, "on_timeout": "rejected"}),
            Node("send", "action", {"action": "send_proposal"}),
        ],
        edges=[
            Edge("draft", "approval"),
            Edge("approval", "send", when="approved"),
            # "rejected" and timeouts have no outgoing edge → execution ends.
        ],
    )
