"""Wire format of a published flow version, as the workflow receives it.

The source of truth is ``igs_common.flows.schema.FlowDefinition`` (generated from
``packages/flow-schema/flow.schema.json``). Every document is validated through it and
schema defaults are filled in before it becomes workflow input; these dataclasses only exist
because workflow input goes through Temporal's default JSON converter. Graph rules are checked
at publish time by ``igs_common.flows.validate``, not here.
"""

from dataclasses import dataclass, field
from typing import Any

from igs_common.flows.schema import FlowDefinition
from igs_common.flows.validate import ports_for

# Port taken by `onError: continue` (flow-engine.md §11): the node's "normal" exit.
_PRIMARY_PORT: dict[str, str] = {
    "condition": "true",
    "approval": "approved",
    "switch": "default",
    "classify": "default",
    "choice": "no_match",
}


@dataclass
class NodeDef:
    id: str
    type: str
    config: dict[str, Any] = field(default_factory=dict)
    name: str | None = None
    disabled: bool = False
    on_error: str = "fail"  # fail | continue | branch
    retry: dict[str, Any] | None = None
    timeout: str | None = None  # ISO-8601 duration, per attempt

    def success_port(self) -> str:
        if self.type == "agent":
            return "completed" if self.config.get("mode") == "conversation" else "next"
        if self.type in _PRIMARY_PORT:
            return _PRIMARY_PORT[self.type]
        ports = ports_for({"type": self.type, "config": self.config})
        return "next" if "next" in ports or not ports else sorted(ports)[0]


@dataclass
class EdgeDef:
    source: str
    target: str
    port: str = "next"


@dataclass
class FlowVersion:
    flow_id: str
    version: int
    entry: str
    nodes: list[NodeDef]
    edges: list[EdgeDef]
    settings: dict[str, Any] = field(default_factory=dict)
    trigger_type: str = "manual"

    def node(self, node_id: str) -> NodeDef:
        for n in self.nodes:
            if n.id == node_id:
                return n
        raise KeyError(node_id)

    def target(self, node_id: str, port: str) -> str | None:
        for e in self.edges:
            if e.source == node_id and e.port == port:
                return e.target
        return None

    @property
    def max_steps(self) -> int:
        return int(self.settings.get("maxSteps") or 500)

    @property
    def conversation_idle_timeout(self) -> str:
        conversation = self.settings.get("conversation") or {}
        return str(conversation.get("idleTimeout") or "PT30M")

    @classmethod
    def from_definition(
        cls, definition: FlowDefinition, version: int | None = None
    ) -> "FlowVersion":
        doc = definition.model_dump(mode="json", by_alias=True, exclude_none=True)
        v = version if version is not None else definition.version
        if v is None:
            raise ValueError("a published flow version needs a version number")
        nodes = [
            NodeDef(
                id=n["id"],
                type=n["type"],
                config=n.get("config") or {},
                name=n.get("name"),
                disabled=n.get("disabled", False),
                on_error=n.get("onError", "fail"),
                retry=n.get("retry"),
                timeout=n.get("timeout"),
            )
            for n in doc["nodes"]
        ]
        edges = [EdgeDef(e["from"], e["to"], e.get("port", "next")) for e in doc["edges"]]
        return cls(
            flow_id=doc["id"],
            version=int(v),
            entry=doc["entry"],
            nodes=nodes,
            edges=edges,
            settings=doc.get("settings") or {},
            trigger_type=doc["trigger"]["type"],
        )

    @classmethod
    def from_json(cls, doc: dict[str, Any], version: int | None = None) -> "FlowVersion":
        """Validate a ``flow.schema.json`` document (the pinned published version)."""
        return cls.from_definition(FlowDefinition.model_validate(doc), version)
