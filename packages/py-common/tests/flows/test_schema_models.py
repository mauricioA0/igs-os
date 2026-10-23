import json
from pathlib import Path

import pytest
from pydantic import ValidationError

from igs_common.flows.schema import AgentNode, FlowDefinition, ModelRef, WaitNode

NAMES = ["inbound-inquiry", "post-match-report", "pre-departure-check"]
NODE_CLASSES = {
    f"{t}Node"
    for t in (
        "Agent Extract Classify KnowledgeSearch Say Capture Choice Condition Switch Set "
        "Map Subflow Wait End Http Action SendMessage EmitEvent Approval"
    ).split()
}


def test_every_example_is_covered(flow_schema_dir: Path) -> None:
    assert sorted(p.stem for p in (flow_schema_dir / "examples").glob("*.json")) == NAMES


@pytest.mark.parametrize("name", NAMES)
def test_examples_parse_into_tagged_models(example, name: str) -> None:
    flow = FlowDefinition.model_validate(example(name))
    assert {type(n.root).__name__ for n in flow.nodes} <= NODE_CLASSES


@pytest.mark.parametrize("name", NAMES)
def test_examples_match_the_json_schema(example, flow_schema_dir: Path, name: str) -> None:
    jsonschema = pytest.importorskip("jsonschema")
    schema = json.loads((flow_schema_dir / "flow.schema.json").read_text())
    jsonschema.Draft202012Validator(schema).validate(example(name))


def test_models_are_provider_neutral(example, flow_schema_dir: Path) -> None:
    flow = FlowDefinition.model_validate(example("inbound-inquiry"))
    agent = next(n.root for n in flow.nodes if isinstance(n.root, AgentNode))
    assert agent.config.model == ModelRef(role="agent")
    assert "claude" not in (flow_schema_dir / "flow.schema.json").read_text()


def test_discriminator_rejects_unknown_node_type(example) -> None:
    raw = example("post-match-report")
    raw["nodes"][0]["type"] = "javascript"
    with pytest.raises(ValidationError, match="javascript"):
        FlowDefinition.model_validate(raw)


def test_round_trip(example) -> None:
    flow = FlowDefinition.model_validate(example("pre-departure-check"))
    assert any(isinstance(n.root, WaitNode) for n in flow.nodes)
    dumped = flow.model_dump(mode="json", by_alias=True, exclude_unset=True)
    assert FlowDefinition.model_validate(dumped) == flow
