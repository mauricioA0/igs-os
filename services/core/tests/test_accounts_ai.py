"""Account 360 AI routes with a fake service (no DB, no LLM)."""

from collections.abc import AsyncIterator
from datetime import UTC, datetime
from uuid import UUID

import httpx
import pytest
from core_test_support import API_KEY, DEMO_TENANT

from igs_common.accounts import AccountNotFoundError, Answer, Brief, Citation
from igs_common.db.enums import AccountHealth
from igs_common.llm import LLMError, Usage
from igs_core.api.v1 import accounts_ai
from igs_core.app import create_app
from igs_core.config import Settings
from igs_core.repositories import Repositories

ACCOUNT = UUID(int=7)
CITATIONS = (
    Citation(n=1, interaction_id=None, label="Registro del sistema (IGS OS)"),
    Citation(n=2, interaction_id=UUID(int=70), label="email · 20/10/2026 · Robert Haines"),
)


class FakeIntelligence:
    def __init__(self) -> None:
        self.calls: list[tuple[str, UUID, UUID, object]] = []
        self.fail: Exception | None = None

    async def brief(self, *, tenant_id: UUID, account_id: UUID, refresh: bool = False):  # noqa: ANN201
        self.calls.append(("brief", tenant_id, account_id, refresh))
        if self.fail:
            raise self.fail
        if account_id != ACCOUNT:
            raise AccountNotFoundError(str(account_id))
        brief = Brief(
            account_id=ACCOUNT,
            text="Gira confirmada. [1] PO aprobada el 20/10. [2]",
            citations=CITATIONS,
            health=AccountHealth.AMBER,
            health_reasons=("Saldo vencido de US$ 48,552 (vencía el 30/09)",),
            inputs_hash="sha256:x",
            model="gpt-6.1-sol",
            generated_at=datetime(2026, 10, 22, 13, tzinfo=UTC),
        )
        return brief, not refresh

    async def ask(self, *, tenant_id: UUID, account_id: UUID, question: str) -> Answer:
        self.calls.append(("ask", tenant_id, account_id, question))
        if self.fail:
            raise self.fail
        return Answer(
            question=question,
            text="Robert Haines firma los contratos. [1]",
            citations=CITATIONS[1:],
            grounded=True,
            model="gpt-6.1-sol",
            usage=Usage(),
        )


@pytest.fixture
def service() -> FakeIntelligence:
    return FakeIntelligence()


@pytest.fixture
async def ai_client(
    settings: Settings, repos: Repositories, service: FakeIntelligence
) -> AsyncIterator[httpx.AsyncClient]:
    app = create_app(settings, repos=repos)
    app.include_router(accounts_ai.router, prefix="/v1")
    app.dependency_overrides[accounts_ai.get_account_intelligence] = lambda: service
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as c:
        yield c


async def test_brief_returns_cited_text_and_health(
    ai_client: httpx.AsyncClient, service: FakeIntelligence
) -> None:
    res = await ai_client.get(f"/v1/accounts/{ACCOUNT}/brief")
    assert res.status_code == 200
    body = res.json()
    assert body["cached"] is True and body["health"] == "amber"
    assert body["citations"][0] == {
        "n": 1,
        "interaction_id": None,
        "label": "Registro del sistema (IGS OS)",
    }
    assert body["citations"][1]["interaction_id"] == str(UUID(int=70))
    assert service.calls == [("brief", DEMO_TENANT, ACCOUNT, False)]


async def test_demo_cannot_force_refresh_but_api_keys_can(
    ai_client: httpx.AsyncClient, service: FakeIntelligence
) -> None:
    res = await ai_client.get(f"/v1/accounts/{ACCOUNT}/brief", params={"refresh": "true"})
    assert res.status_code == 403
    assert res.headers["content-type"].startswith("application/problem+json")
    assert service.calls == []

    res = await ai_client.get(
        f"/v1/accounts/{ACCOUNT}/brief",
        params={"refresh": "true"},
        headers={"Authorization": f"Bearer {API_KEY}"},
    )
    assert res.status_code == 200 and res.json()["cached"] is False


async def test_unknown_account_is_404(ai_client: httpx.AsyncClient) -> None:
    res = await ai_client.get(f"/v1/accounts/{UUID(int=404)}/brief")
    assert res.status_code == 404
    assert res.json()["type"].endswith("/not-found")


async def test_llm_failures_are_502(
    ai_client: httpx.AsyncClient, service: FakeIntelligence
) -> None:
    service.fail = LLMError("boom")
    assert (await ai_client.get(f"/v1/accounts/{ACCOUNT}/brief")).status_code == 502
    res = await ai_client.post(f"/v1/accounts/{ACCOUNT}/ask", json={"question": "Who decides?"})
    assert res.status_code == 502
    assert "boom" not in res.text


async def test_ask_returns_grounded_answer(
    ai_client: httpx.AsyncClient, service: FakeIntelligence
) -> None:
    res = await ai_client.post(
        f"/v1/accounts/{ACCOUNT}/ask", json={"question": "¿Quién decide en Lakeshore?"}
    )
    assert res.status_code == 200
    body = res.json()
    assert body["grounded"] is True and body["citations"][0]["n"] == 2
    assert service.calls == [("ask", DEMO_TENANT, ACCOUNT, "¿Quién decide en Lakeshore?")]


async def test_ask_validates_question(ai_client: httpx.AsyncClient) -> None:
    res = await ai_client.post(f"/v1/accounts/{ACCOUNT}/ask", json={"question": "?"})
    assert res.status_code == 422
