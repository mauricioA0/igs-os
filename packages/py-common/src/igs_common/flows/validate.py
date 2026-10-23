"""Publish-time validation of flow definitions.

Spec: docs/architecture/flow-engine.md §13 (rules 1-8) and docs/architecture/security.md
(tool classes). JSON Schema / the generated Pydantic models cover structure; this module
covers what a schema can't: ids and references, ports per node type, reachability,
expressions, registry lookups and the security rule.

Security rule: when the trigger carries untrusted input (`chat`, `webhook`), every node
with external or destructive effects must be reachable from the entry **only** through
the `approved` port of an `approval` node. Agent nodes count as external when they can
call an external tool that is not listed in `approvalRequiredFor`.

`validate_flow` never raises for a bad definition; it returns every problem it finds so
the editor can show them all at once.
"""

from __future__ import annotations

from collections import deque
from collections.abc import Iterable, Mapping
from dataclasses import dataclass, field
from typing import Any, Literal

from pydantic import ValidationError

from igs_common.flows import cel
from igs_common.flows.schema import FlowDefinition

Severity = Literal["error", "warning"]

UNTRUSTED_TRIGGERS = frozenset({"chat", "webhook"})
CONVERSATION_NODES = frozenset({"say", "capture", "choice"})
MAX_STEPS = 5_000
MAX_SUBFLOW_DEPTH = 5

# Domain action registry (flow-engine.md §7.4): action → required input keys.
DOMAIN_ACTIONS: dict[str, frozenset[str]] = {
    "create_lead": frozenset({"lead"}),
    "update_lead_status": frozenset({"leadId", "status"}),
    "draft_trip": frozenset({"leadId"}),
    "get_trip": frozenset({"tripId"}),
    "list_trip_items": frozenset({"tripId"}),
    "update_trip_item": frozenset({"itemId"}),
    "swap_opponent": frozenset({"itemId", "opponentId"}),
    "set_trip_status": frozenset({"tripId", "status"}),
    "request_provider_confirmations": frozenset({"tripId", "replyBy"}),
    "send_proposal": frozenset({"tripId", "to"}),
    "create_ops_task": frozenset({"title"}),
    "check_trip_readiness": frozenset({"tripId"}),
}
# Optional input keys accepted besides the required ones (anything else is an error).
DOMAIN_ACTION_OPTIONAL: dict[str, frozenset[str]] = {
    "create_lead": frozenset({"conversationId"}),
    "update_trip_item": frozenset({"status", "notes"}),
    "list_trip_items": frozenset({"statuses", "withProvider"}),
    "request_provider_confirmations": frozenset({"onlyStatuses"}),
    "send_proposal": frozenset({"note"}),
}
# create_ops_task takes extra context keys by design.
OPEN_INPUT_ACTIONS = frozenset({"create_ops_task"})

# security.md "Tool classes": write-external / destructive actions and tools.
EXTERNAL_ACTIONS = frozenset({"send_proposal", "request_provider_confirmations"})
EXTERNAL_TOOLS = frozenset(
    {
        "send_message",
        "send_proposal",
        "request_provider_confirmation",
        "request_provider_confirmations",
        "set_trip_status",
    }
)


@dataclass(frozen=True)
class Problem:
    code: str
    message: str
    severity: Severity = "error"
    node_id: str | None = None
    path: str | None = None  # JSON pointer into the definition, when it helps the editor

    def as_dict(self) -> dict[str, Any]:
        return {k: v for k, v in self.__dict__.items() if v is not None}


@dataclass
class Registry:
    """What exists for the tenant. `None` means "unknown here": the check is skipped."""

    flows: frozenset[str] | None = None
    tools: frozenset[str] | None = None
    knowledge_bases: frozenset[str] | None = None
    secrets: frozenset[str] | None = None


@dataclass
class ValidationResult:
    problems: list[Problem] = field(default_factory=list)
    definition: FlowDefinition | None = None

    @property
    def ok(self) -> bool:
        return not any(p.severity == "error" for p in self.problems)

    @property
    def errors(self) -> list[Problem]:
        return [p for p in self.problems if p.severity == "error"]

    @property
    def warnings(self) -> list[Problem]:
        return [p for p in self.problems if p.severity == "warning"]


def validate_flow(
    raw: Mapping[str, Any],
    *,
    registry: Registry | None = None,
    conversation_subflow: bool = False,
) -> ValidationResult:
    """Validate a flow definition (a JSON object) for publishing.

    `conversation_subflow`: the flow is only ever called from chat-triggered flows, so
    conversation nodes are allowed without a `chat` trigger (rule 6).
    """
    result = ValidationResult()
    try:
        result.definition = FlowDefinition.model_validate(raw)
    except ValidationError as exc:
        for err in exc.errors():
            loc = "/" + "/".join(str(p) for p in err["loc"])
            result.problems.append(Problem("schema", f"{loc}: {err['msg']}", path=loc))
        return result
    _Checker(raw, result, registry or Registry(), conversation_subflow).run()
    return result


# ── Ports ───────────────────────────────────────────────────────────────────


def ports_for(node: Mapping[str, Any]) -> frozenset[str]:
    """Output ports a node can choose on success (plus `error` when onError=branch)."""
    kind, config = node["type"], node.get("config") or {}
    if node.get("disabled"):
        ports: set[str] = {"next"}
    elif kind == "agent":
        ports = {"completed", "handoff"} if config.get("mode") == "conversation" else {"next"}
    elif kind == "classify":
        ports = {c["id"] for c in config.get("classes", [])} | {"default"}
    elif kind == "capture":
        ports = {"next", "timeout"}
    elif kind == "choice":
        ports = {o["id"] for o in config.get("options", [])} | {"no_match", "timeout"}
    elif kind == "condition":
        ports = {"true", "false"}
    elif kind == "switch":
        ports = {c["id"] for c in config.get("cases", [])} | {"default"}
    elif kind == "approval":
        ports = {"approved", "rejected", "expired"}
    elif kind == "end":
        ports = set()
    else:
        ports = {"next"}
    if node.get("onError") == "branch":
        ports.add("error")
    return frozenset(ports)


# ── Checker ─────────────────────────────────────────────────────────────────


class _Checker:
    def __init__(
        self,
        raw: Mapping[str, Any],
        result: ValidationResult,
        registry: Registry,
        conversation_subflow: bool,
    ) -> None:
        self.raw = raw
        self.result = result
        self.registry = registry
        self.conversation_subflow = conversation_subflow
        self.nodes: dict[str, Mapping[str, Any]] = {}
        self.node_index: dict[str, int] = {}
        self.edges: list[Mapping[str, Any]] = list(raw.get("edges", []))
        self.out: dict[str, dict[str, str]] = {}  # node → port → target

    def add(self, code: str, message: str, **kw: Any) -> None:
        self.result.problems.append(Problem(code, message, **kw))

    def run(self) -> None:
        self.check_conditional_config()
        self.check_ids()
        self.check_edges()
        self.check_reachability()
        self.check_expressions()
        self.check_registry()
        self.check_conversation_nodes()
        self.check_settings()
        self.check_security()

    # Conditional requirements from the JSON Schema (if/then) that the generated models
    # don't enforce.
    def check_conditional_config(self) -> None:
        for i, node in enumerate(self.raw["nodes"]):
            cfg, kind, nid = node.get("config") or {}, node["type"], node["id"]
            path = f"/nodes/{i}/config"
            if kind == "agent":
                mode = cfg.get("mode")
                need, forbid = ("input", "exit") if mode == "task" else ("exit", "input")
                if need not in cfg:
                    self.add(
                        "config_missing_field",
                        f"{mode} agent '{nid}' needs '{need}'",
                        node_id=nid,
                        path=path,
                    )
                if forbid in cfg:
                    self.add(
                        "config_unexpected_field",
                        f"{mode} agent '{nid}' can't have '{forbid}'",
                        node_id=nid,
                        path=f"{path}/{forbid}",
                    )
            elif kind == "wait":
                mode = cfg.get("mode")
                if mode in ("duration", "until") and mode not in cfg:
                    self.add(
                        "config_missing_field",
                        f"wait '{nid}' in {mode} mode needs '{mode}'",
                        node_id=nid,
                        path=path,
                    )

    # Rule 1: unique ids and references.
    def check_ids(self) -> None:
        for i, node in enumerate(self.raw["nodes"]):
            nid = node["id"]
            if nid in self.nodes:
                self.add(
                    "duplicate_node_id",
                    f"node id '{nid}' is used twice",
                    node_id=nid,
                    path=f"/nodes/{i}/id",
                )
                continue
            self.nodes[nid] = node
            self.node_index[nid] = i
        entry = self.raw["entry"]
        if entry not in self.nodes:
            self.add("unknown_entry", f"entry '{entry}' is not a node", path="/entry")
        for j, interrupt in enumerate(self.interrupts()):
            if interrupt.get("goTo") not in self.nodes:
                self.add(
                    "unknown_interrupt_target",
                    f"interrupt '{interrupt.get('id')}' goes to unknown node "
                    f"'{interrupt.get('goTo')}'",
                    path=f"/settings/conversation/interrupts/{j}/goTo",
                )

    # Rule 2: ports valid for the node type, one edge per port.
    def check_edges(self) -> None:
        for i, edge in enumerate(self.edges):
            src, dst, port = edge["from"], edge["to"], edge.get("port", "next")
            path = f"/edges/{i}"
            if src not in self.nodes:
                self.add("unknown_edge_source", f"edge from unknown node '{src}'", path=path)
                continue
            if dst not in self.nodes:
                self.add(
                    "unknown_edge_target", f"edge to unknown node '{dst}'", node_id=src, path=path
                )
                continue
            valid = ports_for(self.nodes[src])
            if port not in valid:
                hint = ", ".join(sorted(valid)) or "none (end node)"
                if port == "error":
                    hint += "; set onError: branch to use the error port"
                self.add(
                    "invalid_port",
                    f"'{src}' has no port '{port}' (valid: {hint})",
                    node_id=src,
                    path=path,
                )
                continue
            ports = self.out.setdefault(src, {})
            if port in ports:
                self.add(
                    "duplicate_port_edge",
                    f"port '{port}' of '{src}' has more than one edge",
                    node_id=src,
                    path=path,
                )
                continue
            ports[port] = dst

    # Rule 3: reachability and dead ends.
    def check_reachability(self) -> None:
        starts = [self.raw["entry"], *(i.get("goTo") for i in self.interrupts())]
        seen = self.reach(s for s in starts if s in self.nodes)
        for nid, node in self.nodes.items():
            if nid not in seen:
                self.add(
                    "unreachable_node",
                    f"'{nid}' can't be reached from the entry",
                    node_id=nid,
                    path=f"/nodes/{self.node_index[nid]}",
                )
            if node["type"] != "end" and not self.out.get(nid):
                self.add(
                    "dead_end",
                    f"'{nid}' has no outgoing edge",
                    node_id=nid,
                    path=f"/nodes/{self.node_index[nid]}",
                )

    # Rule 4: expressions compile, scopes exist, node references make sense.
    def check_expressions(self) -> None:
        ancestors = self.ancestors()
        for path, text, kind in _expressions(self.raw):
            node_id = _node_id_from_path(self.raw, path)
            try:
                if kind == "expression":
                    compiled = [cel.compile_expression(text)]
                else:
                    compiled = list(cel.compile_template(text).expressions)
            except cel.ExpressionError as exc:
                self.add(f"expression_{exc.kind}", exc.message, node_id=node_id, path=path)
                continue
            for expr in compiled:
                for ref in sorted(expr.node_refs):
                    if ref not in self.nodes:
                        self.add(
                            "unknown_node_reference",
                            f"expression references unknown node '{ref}'",
                            node_id=node_id,
                            path=path,
                        )
                    elif node_id and node_id != ref and ref not in ancestors.get(node_id, set()):
                        self.add(
                            "node_reference_order",
                            f"'{node_id}' reads nodes.{ref}, which can't run before it",
                            severity="warning",
                            node_id=node_id,
                            path=path,
                        )

    # Rule 5: registry lookups.
    def check_registry(self) -> None:
        reg = self.registry
        for nid, node in self.nodes.items():
            cfg = node.get("config") or {}
            base = f"/nodes/{self.node_index[nid]}/config"
            if node["type"] == "action":
                action = str(cfg.get("action"))
                required = DOMAIN_ACTIONS.get(action)
                if required is None:
                    self.add(
                        "unknown_action",
                        f"action '{action}' is not in the registry",
                        node_id=nid,
                        path=f"{base}/action",
                    )
                    continue
                inputs = set((cfg.get("inputs") or {}).keys())
                missing = required - inputs
                if missing:
                    self.add(
                        "action_missing_inputs",
                        f"action '{action}' needs {', '.join(sorted(missing))}",
                        node_id=nid,
                        path=f"{base}/inputs",
                    )
                allowed = required | DOMAIN_ACTION_OPTIONAL.get(action, frozenset())
                extra = inputs - allowed
                if extra and action not in OPEN_INPUT_ACTIONS:
                    self.add(
                        "action_unknown_inputs",
                        f"action '{action}' doesn't take {', '.join(sorted(extra))}",
                        node_id=nid,
                        path=f"{base}/inputs",
                    )
            if reg.tools is not None:
                for tool in cfg.get("tools", []):
                    if tool not in reg.tools:
                        self.add(
                            "unknown_tool",
                            f"tool '{tool}' is not registered",
                            node_id=nid,
                            path=f"{base}/tools",
                        )
            if reg.knowledge_bases is not None:
                for kb in cfg.get("knowledgeBases", []):
                    if kb not in reg.knowledge_bases:
                        self.add(
                            "unknown_knowledge_base",
                            f"knowledge base '{kb}' not found",
                            node_id=nid,
                            path=f"{base}/knowledgeBases",
                        )
            if reg.flows is not None and node["type"] in ("map", "subflow"):
                if cfg.get("flow") not in reg.flows:
                    self.add(
                        "unknown_flow",
                        f"flow '{cfg.get('flow')}' not found",
                        node_id=nid,
                        path=f"{base}/flow",
                    )
            if reg.secrets is not None:
                for ref in _secret_refs(cfg):
                    if ref not in reg.secrets:
                        self.add(
                            "unknown_secret", f"secret '{ref}' not found", node_id=nid, path=base
                        )

    # Rule 6: conversation nodes only in chat flows.
    def check_conversation_nodes(self) -> None:
        if self.raw["trigger"]["type"] == "chat" or self.conversation_subflow:
            return
        for nid, node in self.nodes.items():
            mode = (node.get("config") or {}).get("mode")
            if node["type"] in CONVERSATION_NODES or (
                node["type"] == "agent" and mode == "conversation"
            ):
                self.add(
                    "conversation_node_without_chat",
                    f"'{nid}' talks to a user, but the flow isn't started by chat",
                    node_id=nid,
                    path=f"/nodes/{self.node_index[nid]}",
                )

    # Rules 7 and 8: error flow and limits.
    def check_settings(self) -> None:
        settings = self.raw.get("settings") or {}
        if settings.get("errorFlow") == self.raw["id"]:
            self.add(
                "error_flow_self", "a flow can't be its own error flow", path="/settings/errorFlow"
            )
        if self.registry.flows is not None and settings.get("errorFlow"):
            if settings["errorFlow"] not in self.registry.flows:
                self.add(
                    "unknown_error_flow",
                    f"error flow '{settings['errorFlow']}' not found",
                    path="/settings/errorFlow",
                )
        if (settings.get("maxSteps") or 0) > MAX_STEPS:
            self.add("limit_max_steps", f"maxSteps above {MAX_STEPS}", path="/settings/maxSteps")
        trigger = self.raw["trigger"]
        if trigger["type"] == "webhook" and (trigger.get("auth") or {}).get("type") == "none":
            self.add(
                "webhook_without_auth",
                "webhook trigger accepts unauthenticated calls",
                severity="warning",
                path="/trigger/auth",
            )

    # Security rule: untrusted input → external effects only behind an approval.
    def check_security(self) -> None:
        trigger = self.raw["trigger"]["type"]
        if trigger not in UNTRUSTED_TRIGGERS:
            return
        starts = [self.raw["entry"], *(i.get("goTo") for i in self.interrupts())]
        parent: dict[str, str | None] = {}
        queue: deque[str] = deque()
        for s in starts:
            if s in self.nodes and s not in parent:
                parent[s] = None
                queue.append(s)
        while queue:
            nid = queue.popleft()
            for port, dst in self.out.get(nid, {}).items():
                if self.nodes[nid]["type"] == "approval" and port == "approved":
                    continue  # guarded from here on
                if dst not in parent:
                    parent[dst] = nid
                    queue.append(dst)
        for nid in parent:
            reason = self.external_reason(self.nodes[nid])
            if reason:
                route = " → ".join(_path_to(parent, nid))
                self.add(
                    "unguarded_external_action",
                    f"'{nid}' {reason} and can run on {trigger} input without an approval "
                    f"(path: {route}). Add an approval node before it.",
                    node_id=nid,
                    path=f"/nodes/{self.node_index[nid]}",
                )

    @staticmethod
    def external_reason(node: Mapping[str, Any]) -> str | None:
        kind, cfg = node["type"], node.get("config") or {}
        if node.get("disabled"):
            return None
        if kind == "send_message" and cfg.get("channel") != "ops_inbox":
            return f"sends a {cfg.get('channel')} message"
        if kind == "http" and cfg.get("method", "GET") != "GET":
            return f"makes an outbound {cfg.get('method')} request"
        if kind == "action":
            action = cfg.get("action")
            if action in EXTERNAL_ACTIONS:
                return f"runs external action '{action}'"
            if action == "set_trip_status":
                status = (cfg.get("inputs") or {}).get("status")
                if (
                    not isinstance(status, str)
                    or cel.has_placeholders(status)
                    or (status == "cancelled")
                ):
                    return "can cancel a trip"
        if kind == "agent":
            gated = set(cfg.get("approvalRequiredFor", []))
            risky = sorted(set(cfg.get("tools", [])) & EXTERNAL_TOOLS - gated)
            if risky:
                return f"lets the agent call {', '.join(risky)} without approvalRequiredFor"
        return None

    # Graph helpers.
    def interrupts(self) -> list[Mapping[str, Any]]:
        settings = self.raw.get("settings") or {}
        return list((settings.get("conversation") or {}).get("interrupts") or [])

    def reach(self, starts: Iterable[str]) -> set[str]:
        seen: set[str] = set()
        queue = deque(starts)
        while queue:
            nid = queue.popleft()
            if nid in seen:
                continue
            seen.add(nid)
            queue.extend(self.out.get(nid, {}).values())
        return seen

    def ancestors(self) -> dict[str, set[str]]:
        """node → nodes that can run before it on some path (reverse reachability)."""
        reverse: dict[str, set[str]] = {}
        for src, ports in self.out.items():
            for dst in ports.values():
                reverse.setdefault(dst, set()).add(src)
        result: dict[str, set[str]] = {}
        for nid in self.nodes:
            seen: set[str] = set()
            queue = deque(reverse.get(nid, ()))
            while queue:
                cur = queue.popleft()
                if cur in seen:
                    continue
                seen.add(cur)
                queue.extend(reverse.get(cur, ()))
            result[nid] = seen
        return result


# ── Expression discovery ────────────────────────────────────────────────────

_EXPRESSION_FIELDS = frozenset({"expression", "filter"})


def _expressions(raw: Mapping[str, Any]) -> Iterable[tuple[str, str, str]]:
    """Yield (json pointer, text, kind) for every expression or template in the flow.

    kind is `expression` for raw-CEL fields (`condition.expression`, switch cases, trigger
    `filter`) and `template` for any other string containing `{{ }}`. JSON Schema
    sub-documents (`output`, `schema`, `input` of manual/webhook triggers) are skipped.
    """

    def walk(value: Any, path: str, key: str | None) -> Iterable[tuple[str, str, str]]:
        if isinstance(value, str):
            if key in _EXPRESSION_FIELDS:
                yield path, value, "expression"
            elif "{{" in value or "}}" in value:
                yield path, value, "template"
        elif isinstance(value, Mapping):
            for k, v in value.items():
                if k in ("output", "schema") and isinstance(v, Mapping) and "type" in v:
                    continue
                yield from walk(v, f"{path}/{k}", k)
        elif isinstance(value, list):
            for i, v in enumerate(value):
                yield from walk(v, f"{path}/{i}", key)

    trigger = raw.get("trigger") or {}
    if isinstance(trigger.get("filter"), str):
        yield "/trigger/filter", trigger["filter"], "expression"
    for i, node in enumerate(raw.get("nodes", [])):
        yield from walk(node.get("config") or {}, f"/nodes/{i}/config", None)
    settings = raw.get("settings") or {}
    yield from walk(settings, "/settings", None)


def _node_id_from_path(raw: Mapping[str, Any], path: str) -> str | None:
    parts = path.split("/")
    if len(parts) > 2 and parts[1] == "nodes":
        return raw["nodes"][int(parts[2])]["id"]
    return None


def _secret_refs(cfg: Any) -> Iterable[str]:
    if isinstance(cfg, Mapping):
        for k, v in cfg.items():
            if k == "secretRef" and isinstance(v, str):
                yield v
            else:
                yield from _secret_refs(v)
    elif isinstance(cfg, list):
        for v in cfg:
            yield from _secret_refs(v)


def _path_to(parent: Mapping[str, str | None], nid: str) -> list[str]:
    route = [nid]
    while (prev := parent.get(route[-1])) is not None:
        route.append(prev)
    return list(reversed(route))
