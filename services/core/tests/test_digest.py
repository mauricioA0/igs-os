"""GET /v1/digest/today and the `daily_digest` MCP tool (SQL loading: py-common digest tests)."""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import UUID

import httpx
import pytest
from agent_test_support import FakeOpsBackend, principal
from core_test_support import DEMO_TENANT
from mcp import Client

from igs_common.digest import ApprovalInput, DigestInputs, LeadInput
from igs_common.llm import FakeLLM, Scripted
from igs_core.api.v1 import digest as digest_api
from igs_core.app import create_app
from igs_core.config import Settings
from igs_core.mcp.server import build_mcp_server, current_principal
from igs_core.repositories import Repositories

NOW = datetime.now(UTC)
APPROVAL = ApprovalInput(
    id=UUID(int=9003),
    title="Enviar la propuesta IGS-2711 a Dana Whitfield",
    created_at=NOW - timedelta(hours=20),
    expires_at=None,
    subject_type="trip",
    subject_id=UUID(int=300),
)
LEAD = LeadInput(
    id=UUID(int=500),
    status="new",
    created_at=NOW - timedelta(days=6),
    organization="Harbor Point Academy",
    contact_name="Lee Carter",
    sport="basketball",
    group_size=16,
    answered=False,
)


@asynccontextmanager
async def no_session(_tenant_id: UUID) -> AsyncIterator[None]:
    yield None


@pytest.fixture
def loaded(monkeypatch: pytest.MonkeyPatch) -> list[UUID]:
    calls: list[UUID] = []

    async def fake_load(_session: Any, *, tenant_id: UUID, now: datetime) -> DigestInputs:
        calls.append(tenant_id)
        return DigestInputs(approvals=(APPROVAL,), leads=(LEAD,))

    monkeypatch.setattr(digest_api, "load_digest_inputs", fake_load)
    return calls


def make_client(llm: FakeLLM | None) -> httpx.AsyncClient:
    settings = Settings(environment="test", demo_mode=True, web_base_url="https://ops.example/")
    unused: Any = None  # the digest reads through its own loader, not the repositories
    app = create_app(
        settings, repos=Repositories(directory=_Directory(), trips=unused, accounts=unused)
    )
    app.state.tenant_session = no_session
    app.state.llm = llm
    return httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test")


class _Directory:
    async def tenant_id_by_slug(self, slug: str) -> UUID | None:
        return DEMO_TENANT

    async def principal_for_api_key(self, key_hash: str) -> None:
        return None

    async def ping(self) -> None:
        return None


async def test_json_digest_with_a_checked_model_summary(loaded: list[UUID]) -> None:
    llm = FakeLLM(
        [Scripted(json={"summary": "Hay 1 aprobación esperando y 1 lead sin respuesta."})]
    )
    async with make_client(llm) as client:
        r = await client.get("/v1/digest/today")
        again = await client.get("/v1/digest/today")
    assert r.status_code == 200
    body = r.json()
    assert body["summary_source"] == "llm"
    assert body["facts"]["counts"]["approvals_pending"] == 1
    assert body["facts"]["stale_leads"][0]["organization"] == "Harbor Point Academy"
    assert "https://ops.example/ops/approvals?id=" in body["text"]
    assert loaded == [DEMO_TENANT, DEMO_TENANT]
    # Same facts → the cached summary; the model is called once.
    assert again.json()["summary"] == body["summary"] and len(llm.requests) == 1


async def test_without_a_model_the_template_is_used(
    loaded: list[UUID], monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(digest_api, "digest_llm", lambda _request: None)
    async with make_client(None) as client:
        body = (await client.get("/v1/digest/today")).json()
    assert body["summary_source"] == "template"
    assert body["summary"].startswith("Hoy: 1 aprobación esperando")


async def test_html_and_text_formats(loaded: list[UUID]) -> None:
    async with make_client(FakeLLM([Scripted(json={"summary": "Sin urgencias."})])) as client:
        html = await client.get("/v1/digest/today", params={"format": "html"})
        text = await client.get("/v1/digest/today", params={"format": "text"})
    assert html.headers["content-type"].startswith("text/html")
    assert "Hoy en</span>" in html.text and "<img" not in html.text
    assert text.headers["content-type"].startswith("text/plain")
    assert text.text.startswith("IGS OS · Resumen de operación")


async def test_daily_digest_is_a_read_tool_over_mcp() -> None:
    backend = FakeOpsBackend()
    token = current_principal.set(principal("api_key", "ops", {"igs:read"}))
    try:
        async with Client(build_mcp_server(lambda: backend)) as client:
            tools = {t.name: t for t in (await client.list_tools()).tools}
            result = await client.call_tool("daily_digest", {})
    finally:
        current_principal.reset(token)
    assert tools["daily_digest"].annotations.read_only_hint is True  # type: ignore[union-attr]
    assert not result.is_error
    assert result.structured_content["summary"].startswith("Lo primero")  # type: ignore[index]
