"""Pure checks for the workflow seam: input shape and event trigger matching."""

import json
from pathlib import Path
from uuid import uuid4

import pytest

from igs_common.db.models import OutboxEvent
from igs_core.events.dispatcher import event_workflow_id, trigger_matches
from igs_core.temporal import execution_input

EXAMPLES = Path(__file__).resolve().parents[3] / "packages" / "flow-schema" / "examples"


def _example(name: str) -> dict:
    return json.loads((EXAMPLES / f"{name}.json").read_text())


def test_execution_input_round_trips_into_the_worker_dataclass() -> None:
    worker = pytest.importorskip("igs_worker.workflows.flow_execution", exc_type=ImportError)
    from temporalio.converter import DataConverter

    graph = _example("inbound-inquiry")
    payload = execution_input(
        execution_id="e1",
        tenant_id="t1",
        graph=graph,
        version=3,
        trigger={"message": "hi"},
        vars={"x": 1},
    )
    converter = DataConverter.default.payload_converter
    [encoded] = converter.to_payloads([payload])
    [decoded] = converter.from_payloads([encoded], [worker.ExecutionInput])
    assert decoded.execution_id == "e1"
    assert decoded.tenant_id == "t1"
    assert decoded.flow.version == 3
    assert decoded.flow.entry == graph["entry"]
    assert {n.id for n in decoded.flow.nodes} == {n["id"] for n in graph["nodes"]}
    assert decoded.flow.edges[0].source == graph["edges"][0]["from"]
    assert decoded.trigger == {"message": "hi"}


def _event(type_: str, payload: dict) -> OutboxEvent:
    return OutboxEvent(
        id=uuid4(),
        tenant_id=uuid4(),
        type=type_,
        subject_type="trip",
        subject_id=uuid4(),
        payload=payload,
    )


def test_trigger_matches_event_type_and_cel_filter() -> None:
    graph = _example("pre-departure-check")
    confirmed = {"trip": {"status": "confirmed"}, "previousStatus": "proposed"}
    assert trigger_matches(graph, _event("trip.status_changed", confirmed))
    again = {"trip": {"status": "confirmed"}, "previousStatus": "confirmed"}
    assert not trigger_matches(graph, _event("trip.status_changed", again))
    assert not trigger_matches(graph, _event("trip.created", confirmed))


def test_broken_filter_does_not_match() -> None:
    graph = {"trigger": {"type": "event", "event": "x.y", "filter": "trigger.a.b ==="}}
    assert not trigger_matches(graph, _event("x.y", {}))


def test_event_workflow_id_is_deterministic() -> None:
    e, v = uuid4(), uuid4()
    assert event_workflow_id(e, v) == f"evt-{e}-{v}" == event_workflow_id(e, v)


async def test_api_and_worker_converters_interoperate() -> None:
    """With a shared key, a payload the API encodes is readable by the worker and vice versa."""
    import base64
    import os

    from pydantic import SecretStr

    from igs_core.config import Settings
    from igs_core.temporal import data_converter as api_converter
    from igs_worker.settings import WorkerSettings
    from igs_worker.worker import data_converter as worker_converter

    key = base64.b64encode(os.urandom(32)).decode()
    api = api_converter(Settings(temporal_codec_key=SecretStr(key)))
    wrk = worker_converter(WorkerSettings(codec_key=key))
    assert api.payload_codec is not None and wrk.payload_codec is not None
    [encoded] = await api.encode([{"coach": "Dana Whitfield"}])
    assert b"Whitfield" not in encoded.data
    assert await wrk.decode([encoded], [dict]) == [{"coach": "Dana Whitfield"}]


def test_api_requires_codec_key_in_production() -> None:
    import pytest

    from igs_core.config import Settings
    from igs_core.temporal import data_converter

    # Settings refuses production without the key (see test_settings_production_guards); the
    # converter is a second line of defense for settings built without validation.
    with pytest.raises(RuntimeError):
        data_converter(Settings.model_construct(environment="production", temporal_codec_key=None))
