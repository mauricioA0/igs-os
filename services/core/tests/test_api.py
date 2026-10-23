from uuid import UUID

import httpx
from core_test_support import API_KEY, DEMO_TENANT, OTHER_TENANT, load_export_script

from igs_core.app import create_app
from igs_core.config import Settings
from igs_core.repositories import Repositories

PROBLEM = "application/problem+json"


async def test_health_and_request_id(client: httpx.AsyncClient) -> None:
    r = await client.get("/healthz", headers={"x-request-id": "abc123"})
    assert r.status_code == 200
    assert r.headers["x-request-id"] == "abc123"
    generated = await client.get("/healthz")
    assert len(generated.headers["x-request-id"]) == 32


async def test_readyz_reports_db(client: httpx.AsyncClient, repos: Repositories) -> None:
    assert (await client.get("/readyz")).status_code == 200
    repos.directory.ready = False  # type: ignore[attr-defined]
    r = await client.get("/readyz")
    assert r.status_code == 503
    assert r.json()["checks"]["database"].startswith("error")


async def test_demo_principal_without_credentials(client: httpx.AsyncClient) -> None:
    r = await client.get("/v1/me")
    assert r.status_code == 200
    body = r.json()
    assert body["kind"] == "demo"
    assert body["tenant_id"] == str(DEMO_TENANT)
    assert body["role"] == "viewer"


async def test_api_key_resolves_its_own_tenant(client: httpx.AsyncClient) -> None:
    r = await client.get("/v1/me", headers={"authorization": f"Bearer {API_KEY}"})
    assert r.json()["tenant_id"] == str(OTHER_TENANT)
    assert r.json()["scopes"] == ["trips:read"]


async def test_bad_credentials_are_401_problems(client: httpx.AsyncClient) -> None:
    for header in ("Bearer igs_wrong", "Basic abc", "Bearer some.jwt.token"):
        r = await client.get("/v1/me", headers={"authorization": header})
        assert r.status_code == 401, header
        assert r.headers["content-type"] == PROBLEM
        assert r.headers["www-authenticate"].startswith("Bearer")
        assert r.json()["type"].endswith("/unauthorized")


async def test_demo_disabled_requires_credentials(repos: Repositories) -> None:
    app = create_app(Settings(environment="test", demo_mode=False), repos=repos)
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://t") as c:
        assert (await c.get("/v1/trips")).status_code == 401


async def test_trips_cursor_pagination(client: httpx.AsyncClient) -> None:
    first = (await client.get("/v1/trips")).json()
    assert [t["title"] for t in first["items"]] == ["Trip 1", "Trip 2"]
    second = (await client.get("/v1/trips", params={"cursor": first["next_cursor"]})).json()
    assert [t["title"] for t in second["items"]] == ["Trip 3", "Trip 4"]
    last = (await client.get("/v1/trips", params={"cursor": second["next_cursor"]})).json()
    assert [t["title"] for t in last["items"]] == ["Trip 5"]
    assert last["next_cursor"] is None


async def test_trips_filters_and_validation(client: httpx.AsyncClient) -> None:
    r = await client.get("/v1/trips", params={"from": "2027-03-04", "limit": 10})
    assert [t["title"] for t in r.json()["items"]] == ["Trip 4", "Trip 5"]
    bad = await client.get("/v1/trips", params={"status": "nope"})
    assert bad.status_code == 422
    assert bad.headers["content-type"] == PROBLEM
    assert bad.json()["errors"][0]["loc"] == ["query", "status"]
    assert (await client.get("/v1/trips", params={"cursor": "%%%"})).status_code == 400


async def test_trip_detail_and_404(client: httpx.AsyncClient) -> None:
    r = await client.get(f"/v1/trips/{UUID(int=1)}")
    assert r.status_code == 200
    assert r.json()["items"][0]["kind"] == "arrival"
    missing = await client.get(f"/v1/trips/{UUID(int=999)}")
    assert missing.status_code == 404
    assert missing.json()["instance"] == f"/v1/trips/{UUID(int=999)}"
    assert missing.json()["request_id"]


async def test_accounts_are_tenant_scoped(client: httpx.AsyncClient) -> None:
    demo = await client.get("/v1/accounts")
    assert [a["name"] for a in demo.json()["items"]] == ["Lakeshore University"]
    detail = await client.get(f"/v1/accounts/{UUID(int=7)}")
    assert detail.json()["stakeholders"][0]["role"] == "coach"
    other = await client.get("/v1/accounts", headers={"authorization": f"Bearer {API_KEY}"})
    assert other.json()["items"] == []
    cross = await client.get(
        f"/v1/accounts/{UUID(int=7)}", headers={"authorization": f"Bearer {API_KEY}"}
    )
    assert cross.status_code == 404


async def test_write_side_needs_a_database(client: httpx.AsyncClient) -> None:
    # The fake-repos app has no database: the workflow resources answer 503, not 500.
    for path in ("/v1/approvals", "/v1/flows", "/v1/executions"):
        r = await client.get(path)
        assert r.status_code == 503, path
        assert r.headers["content-type"] == PROBLEM


async def test_cors_allows_vercel_previews(client: httpx.AsyncClient) -> None:
    origin = "https://igs-os-git-main-mauricio.vercel.app"
    r = await client.options(
        "/v1/trips",
        headers={"origin": origin, "access-control-request-method": "GET"},
    )
    assert r.status_code == 200
    assert r.headers["access-control-allow-origin"] == origin
    blocked = await client.options(
        "/v1/trips",
        headers={"origin": "https://evil.example", "access-control-request-method": "GET"},
    )
    assert "access-control-allow-origin" not in blocked.headers


async def test_unhandled_errors_are_problems(repos: Repositories) -> None:
    async def boom(*args, **kwargs):  # noqa: ANN002, ANN003
        raise RuntimeError("secret detail")

    repos.trips.list = boom  # type: ignore[method-assign]
    app = create_app(Settings(environment="test"), repos=repos)
    transport = httpx.ASGITransport(app=app, raise_app_exceptions=False)
    async with httpx.AsyncClient(transport=transport, base_url="http://t") as c:
        r = await c.get("/v1/trips")
    assert r.status_code == 500
    assert r.headers["content-type"] == PROBLEM
    assert "secret" not in r.text


def test_openapi_export_is_deterministic() -> None:
    render = load_export_script().render
    first, second = render(), render()
    assert first == second
    assert '"/v1/accounts/{account_id}"' in first
