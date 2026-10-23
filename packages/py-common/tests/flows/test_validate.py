"""Publish-time validator: the three demo flows pass; each broken flow is rejected with
the right problem code (flow-engine.md §13 + security rule from security.md)."""

from collections.abc import Callable
from typing import Any

import pytest

from igs_common.flows.validate import Registry, ports_for, validate_flow

Flow = dict[str, Any]


def node(flow: Flow, node_id: str) -> dict[str, Any]:
    return next(n for n in flow["nodes"] if n["id"] == node_id)


def codes(flow: Flow, **kw: Any) -> set[str]:
    return {p.code for p in validate_flow(flow, **kw).errors}


@pytest.mark.parametrize("name", ["inbound-inquiry", "post-match-report", "pre-departure-check"])
def test_demo_flows_are_publishable(example, name: str) -> None:
    result = validate_flow(example(name))
    assert result.ok, [p.as_dict() for p in result.problems]
    assert result.definition is not None


# ── The broken flows (each one must be rejected) ────────────────────────────


def unknown_node_type(f: Flow) -> None:
    node(f, "greet")["type"] = "javascript"


def malformed_duration(f: Flow) -> None:
    f["settings"]["timeout"] = "14 days"


def task_agent_without_input(f: Flow) -> None:
    cfg = node(f, "qualify")["config"]
    cfg["mode"] = "task"
    cfg.pop("input", None)


def forged_domain_event(f: Flow) -> None:
    f["nodes"].append(
        {"id": "forge", "type": "emit_event", "config": {"event": "lead.created", "payload": {}}}
    )


def action_outside_registry(f: Flow) -> None:
    node(f, "create_lead")["config"]["action"] = "wire_money"


def duplicate_node_id(f: Flow) -> None:
    node(f, "tell_sent")["id"] = "greet"


def edge_to_missing_node(f: Flow) -> None:
    f["edges"].append({"from": "tell_sent", "port": "error", "to": "nowhere"})


def invalid_port(f: Flow) -> None:
    f["edges"].append({"from": "ops_review", "port": "maybe", "to": "done"})


def unreachable_node(f: Flow) -> None:
    f["nodes"].append({"id": "orphan", "type": "end", "config": {"status": "completed"}})


def bad_expression(f: Flow) -> None:
    node(f, "tell_sent")["config"]["text"] = "Sent! {{ nodes.send_proposal.output.url + }}"


def unknown_scope(f: Flow) -> None:
    node(f, "tell_sent")["config"]["text"] = "{{ secrets.openai_key }}"


def unknown_node_reference(f: Flow) -> None:
    node(f, "tell_sent")["config"]["text"] = "{{ nodes.ghost.output.url }}"


def proposal_without_approval(f: Flow) -> None:
    # Send the proposal straight after drafting: chat input reaches an external action.
    for e in f["edges"]:
        if e["from"] == "tell_in_review":
            e["to"] = "send_proposal"


def rejected_path_sends_anyway(f: Flow) -> None:
    for e in f["edges"]:
        if e["from"] == "ops_review" and e.get("port") == "rejected":
            e["to"] = "send_proposal"


def agent_with_ungated_external_tool(f: Flow) -> None:
    node(f, "qualify")["config"]["tools"] = ["find_opponents", "send_message"]


def error_flow_is_itself(f: Flow) -> None:
    f["settings"]["errorFlow"] = f["id"]


BROKEN: dict[str, tuple[Callable[[Flow], None], str]] = {
    "unknown node type": (unknown_node_type, "schema"),
    "malformed duration": (malformed_duration, "schema"),
    "task agent without input": (task_agent_without_input, "config_missing_field"),
    "flow forges a domain event": (forged_domain_event, "schema"),
    "action outside the registry": (action_outside_registry, "schema"),
    "duplicate node id": (duplicate_node_id, "duplicate_node_id"),
    "edge to a missing node": (edge_to_missing_node, "unknown_edge_target"),
    "invalid port": (invalid_port, "invalid_port"),
    "unreachable node": (unreachable_node, "unreachable_node"),
    "CEL syntax error": (bad_expression, "expression_syntax"),
    "unknown scope": (unknown_scope, "expression_unknown_scope"),
    "reference to a missing node": (unknown_node_reference, "unknown_node_reference"),
    "proposal sent without approval": (proposal_without_approval, "unguarded_external_action"),
    "rejected branch still sends": (rejected_path_sends_anyway, "unguarded_external_action"),
    "agent can message without approval": (
        agent_with_ungated_external_tool,
        "unguarded_external_action",
    ),
    "error flow is itself": (error_flow_is_itself, "error_flow_self"),
}


@pytest.mark.parametrize("case", BROKEN, ids=list(BROKEN))
def test_broken_flow_is_rejected(example, case: str) -> None:
    mutate, expected = BROKEN[case]
    flow = example("inbound-inquiry")
    mutate(flow)
    result = validate_flow(flow)
    assert not result.ok
    assert expected in {p.code for p in result.errors}, [p.as_dict() for p in result.problems]


# ── Focused checks ──────────────────────────────────────────────────────────


def test_problems_point_at_the_node(example) -> None:
    flow = example("inbound-inquiry")
    proposal_without_approval(flow)
    problem = next(p for p in validate_flow(flow).errors if p.code == "unguarded_external_action")
    assert problem.node_id == "send_proposal"
    assert problem.path and problem.path.startswith("/nodes/")
    assert "tell_in_review → send_proposal" in problem.message


def test_gated_agent_tool_is_allowed(example) -> None:
    flow = example("inbound-inquiry")
    cfg = node(flow, "qualify")["config"]
    cfg["tools"] = ["send_message"]
    cfg["approvalRequiredFor"] = ["send_message"]
    assert "unguarded_external_action" not in codes(flow)


def test_trusted_triggers_skip_the_security_rule(example) -> None:
    # pre-departure-check is event-triggered (domain events are trusted input).
    flow = example("pre-departure-check")
    assert flow["trigger"]["type"] == "event"
    assert validate_flow(flow).ok


def test_conversation_nodes_need_a_chat_trigger(example) -> None:
    flow = example("post-match-report")
    flow["nodes"].append({"id": "hello", "type": "say", "config": {"text": "hi"}})
    flow["edges"].append({"from": flow["entry"], "port": "error", "to": "hello"})
    node(flow, flow["entry"])["onError"] = "branch"
    assert "conversation_node_without_chat" in codes(flow)
    assert "conversation_node_without_chat" not in codes(flow, conversation_subflow=True)


def test_error_port_requires_on_error_branch(example) -> None:
    flow = example("inbound-inquiry")
    f_node = node(flow, "draft_trip")
    f_node.pop("onError")
    result = validate_flow(flow)
    problem = next(p for p in result.errors if p.code == "invalid_port")
    assert "onError: branch" in problem.message


def test_registry_checks_are_opt_in(example) -> None:
    flow = example("inbound-inquiry")
    assert validate_flow(flow).ok  # no registry: tenant lookups skipped
    registry = Registry(flows=frozenset(), tools=frozenset(), knowledge_bases=frozenset())
    found = codes(flow, registry=registry)
    assert "unknown_error_flow" in found  # notify-ops-on-failure doesn't exist yet
    registry = Registry(
        flows=frozenset({"notify-ops-on-failure"}),
        tools=frozenset({"find_opponents", "search_knowledge"}),
        knowledge_bases=frozenset({"policies", "destinations"}),
    )
    assert not {"unknown_error_flow", "unknown_flow"} & codes(flow, registry=registry)


def test_action_inputs_are_checked(example) -> None:
    flow = example("inbound-inquiry")
    node(flow, "draft_trip")["config"]["inputs"] = {"lead": "{{ vars.leadId }}"}
    found = codes(flow)
    assert {"action_missing_inputs", "action_unknown_inputs"} <= found


def test_reference_to_a_later_node_is_a_warning(example) -> None:
    flow = example("inbound-inquiry")
    node(flow, "greet")["config"]["text"] = "Hi {{ nodes.tell_sent.output.messageId }}"
    result = validate_flow(flow)
    assert result.ok
    assert "node_reference_order" in {p.code for p in result.warnings}


def test_ports_by_node_type() -> None:
    assert ports_for({"type": "approval"}) == {"approved", "rejected", "expired"}
    assert ports_for({"type": "agent", "config": {"mode": "conversation"}}) == {
        "completed",
        "handoff",
    }
    assert ports_for({"type": "end"}) == frozenset()
    assert ports_for({"type": "http", "onError": "branch"}) == {"next", "error"}
    assert ports_for({"type": "condition", "disabled": True}) == {"next"}
    switch = {"type": "switch", "config": {"cases": [{"id": "big"}, {"id": "small"}]}}
    assert ports_for(switch) == {"big", "small", "default"}
