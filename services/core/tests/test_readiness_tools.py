"""trip_readiness / update_traveler_document: MCP exposure, policy and the shared rule catalog."""

import typing
from collections.abc import Iterator
from contextlib import contextmanager
from uuid import uuid4

from agent_test_support import TRAVELER_ID, TRIP_ID, FakeOpsBackend, principal
from mcp import Client

from igs_common.readiness import load_rules
from igs_core.agent.tools import TOOLS_BY_NAME, UpdateTravelerDocumentIn
from igs_core.mcp.server import build_mcp_server, current_principal


@contextmanager
def as_caller(scopes: set[str]) -> Iterator[None]:
    token = current_principal.set(principal("api_key", "ops", scopes))
    try:
        yield
    finally:
        current_principal.reset(token)


def test_tool_requirement_enum_matches_the_rules() -> None:
    field = UpdateTravelerDocumentIn.model_fields["requirement"]
    assert set(typing.get_args(field.annotation)) == set(load_rules().requirements)


def test_readiness_is_read_and_document_update_is_internal_write() -> None:
    assert TOOLS_BY_NAME["trip_readiness"].tool_class.value == "read"
    assert TOOLS_BY_NAME["update_traveler_document"].tool_class.value == "write-internal"


async def test_read_key_gets_a_compact_report() -> None:
    backend = FakeOpsBackend()
    with as_caller({"igs:read"}):
        async with Client(build_mcp_server(lambda: backend)) as client:
            names = {t.name for t in (await client.list_tools()).tools}
            result = await client.call_tool("trip_readiness", {"trip_id": str(TRIP_ID)})
            missing = await client.call_tool("trip_readiness", {"trip_id": str(uuid4())})
    assert "trip_readiness" in names and "update_traveler_document" not in names
    report = result.structured_content
    assert not result.is_error and report["ready"] is False
    assert "people" not in report
    [person] = report["people_detail"]
    assert [i["requirement"] for i in person["items"]] == ["passport"]  # only what needs action
    assert missing.is_error


async def test_document_update_needs_write_scope_and_is_attributed() -> None:
    backend = FakeOpsBackend()
    args = {"traveler_id": str(TRAVELER_ID), "requirement": "br_evisa", "status": "verified"}
    with as_caller({"igs:read"}):
        async with Client(build_mcp_server(lambda: backend)) as client:
            refused = await client.call_tool("update_traveler_document", args)
    assert refused.is_error and backend.document_updates == []
    with as_caller({"igs:read", "igs:write"}):
        async with Client(build_mcp_server(lambda: backend)) as client:
            ok = await client.call_tool("update_traveler_document", args)
            bad = await client.call_tool(
                "update_traveler_document", args | {"requirement": "passport_scan"}
            )
    assert not ok.is_error and ok.structured_content["status"] == "verified"
    [(_, requirement, status, actor)] = backend.document_updates
    assert (requirement, status, actor.surface) == ("br_evisa", "verified", "mcp")
    assert bad.is_error
