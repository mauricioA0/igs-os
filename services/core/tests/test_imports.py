"""POST /v1/imports against real Postgres (``igs_test_c4api``, created by ``conftest.py``)."""

import os
from collections.abc import AsyncIterator
from typing import Any
from uuid import uuid4

import httpx
import pytest
from sqlalchemy import text

from igs_common.db import session as shared
from igs_common.llm import FakeLLM, Scripted
from igs_common.seed import load
from igs_common.testing import database_url
from igs_core.app import create_app
from igs_core.config import Settings
from igs_core.deps import hash_api_key
from igs_core.temporal import RecordingGateway

URL = database_url("igs_test_c4api", driver="postgresql+asyncpg")
pytestmark = pytest.mark.asyncio(loop_scope="session")

CSV = b"name,kind,country,city\nHarbor Point Academy,colegio,USA,Boston\n"


@pytest.fixture(scope="module")
async def env() -> AsyncIterator[dict[str, Any]]:
    engine = shared.configure(URL)
    try:
        async with shared.system_scope() as session:
            await load(session)
    except OSError:
        await shared.dispose()
        pytest.skip("Postgres not reachable")
    keys = {"admin": f"igs_c4a_{uuid4().hex}", "ops": f"igs_c4o_{uuid4().hex}"}
    async with engine.begin() as conn:
        tenant = await conn.scalar(text("select id from tenants where slug = 'igs'"))
        for name, scopes in (("admin", ["igs:read", "igs:admin"]), ("ops", ["igs:write"])):
            await conn.execute(
                text(
                    "insert into api_keys (id, tenant_id, name, prefix, hash, scopes) "
                    "values (gen_random_uuid(), :tenant, :name, 'igs_', :hash, :scopes)"
                ),
                {
                    "tenant": tenant,
                    "name": name,
                    "hash": hash_api_key(keys[name]),
                    "scopes": scopes,
                },
            )
    os.environ["IGS_DB_APP_ROLE"] = "igs_app"
    app = create_app(
        Settings(
            environment="test",
            database_url=URL,
            demo_tenant_slug="igs",
            mcp_enabled=False,
            import_llm_mapping=True,
            import_max_bytes=64 * 1024,
        ),
        workflows=RecordingGateway(),
    )
    transport = httpx.ASGITransport(app=app)
    async with (
        app.router.lifespan_context(app),
        httpx.AsyncClient(transport=transport, base_url="http://t") as client,
    ):
        yield {
            "client": client,
            "app": app,
            "admin": {"Authorization": f"Bearer {keys['admin']}"},
            "ops": {"Authorization": f"Bearer {keys['ops']}"},
        }
    os.environ.pop("IGS_DB_APP_ROLE", None)
    await shared.dispose()


async def _post(env: dict[str, Any], body: bytes, who: str = "admin", **params: Any):
    headers = env.get(who, {})
    return await env["client"].post(
        "/v1/imports",
        params={"filename": "clientes.csv", **params},
        content=body,
        headers={**headers, "Content-Type": "text/csv"},
    )


async def test_only_admins_can_import(env) -> None:
    demo = await _post(env, CSV, who="nobody")
    assert demo.status_code == 403 and demo.json()["type"].endswith("read-only-demo")
    ops = await _post(env, CSV, who="ops")
    assert ops.status_code == 403 and "igs:admin" in ops.json()["detail"]


async def test_dry_run_is_the_default_then_apply_and_rerun(env) -> None:
    dry = await _post(env, CSV)
    assert dry.status_code == 200, dry.text
    body = dry.json()
    assert body["dry_run"] is True and body["applied"] is False
    assert body["summary"]["accounts"] == {"create": 1, "update": 0, "unchanged": 0}

    applied = (await _post(env, CSV, dry_run="false")).json()
    assert applied["applied"] is True
    accounts = (await env["client"].get("/v1/accounts", headers=env["admin"])).json()["items"]
    assert "Harbor Point Academy" in {a["name"] for a in accounts}

    again = (await _post(env, CSV, dry_run="false")).json()
    assert again["summary"]["accounts"] == {"create": 0, "update": 0, "unchanged": 1}


async def test_errors_come_back_as_a_report_not_a_500(env) -> None:
    res = await _post(env, b"name,kind\nX,club\n", dry_run="false")
    assert res.status_code == 200
    body = res.json()
    assert body["applied"] is False
    assert [i["code"] for i in body["issues"]] == ["missing-column"]


async def test_unreadable_empty_and_oversized_files(env) -> None:
    res = await env["client"].post(
        "/v1/imports",
        params={"filename": "x.xlsx"},
        content=b"not a workbook",
        headers=env["admin"],
    )
    assert res.status_code == 422 and res.json()["type"].endswith("unreadable-file")
    assert (await _post(env, b"")).status_code == 422
    assert (await _post(env, b"a,b\n" + b"x" * 70_000)).status_code == 413


async def test_llm_mapping_uses_the_app_model(env) -> None:
    env["app"].state.llm = FakeLLM(
        [
            Scripted(
                json={
                    "columns": [
                        {"header": "Org", "field": "name", "confidence": 0.9, "reason": "org"},
                        {"header": "Nation", "field": "country", "confidence": 0.9, "reason": "c"},
                    ]
                }
            )
        ]
    )
    try:
        res = await _post(env, b"Org,kind,Nation\nQuay FC,club,USA\n", llm_mapping="true")
    finally:
        env["app"].state.llm = None
    body = res.json()
    cols = {c["header"]: (c["field"], c["source"]) for c in body["sheets"][0]["columns"]}
    assert cols["Org"] == ("name", "llm") and cols["Nation"] == ("country", "llm")
    assert body["summary"]["accounts"]["create"] == 1
