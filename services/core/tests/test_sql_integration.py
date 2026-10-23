"""SQL read models against a real, migrated Postgres with row-level security.

Needs `docker compose up -d db` and a migrated database:

    IGS_TEST_DATABASE_URL=postgresql+asyncpg://igs:igs@localhost:5433/igs_test_p4
    (cd packages/py-common && IGS_DATABASE_URL=$IGS_TEST_DATABASE_URL uv run alembic upgrade head)

Skipped when the database is not reachable.
"""

import os
from collections.abc import AsyncIterator
from datetime import date
from uuid import UUID, uuid4

import httpx
import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine

from igs_common.db import session as shared
from igs_core.app import create_app
from igs_core.config import Settings
from igs_core.deps import hash_api_key
from igs_core.repositories.sql import SqlAccounts, SqlDirectory, SqlTrips

URL = os.environ.get(
    "IGS_TEST_DATABASE_URL", "postgresql+asyncpg://igs:igs@localhost:5433/igs_test_p4"
)
# Module-scoped engine and fixtures share one event loop with the tests.
pytestmark = pytest.mark.asyncio(loop_scope="session")


@pytest.fixture(scope="module")
async def engine() -> AsyncIterator[AsyncEngine]:
    engine = shared.configure(URL)
    try:
        async with engine.connect() as conn:
            exists = await conn.scalar(text("select to_regclass('public.account_facts')"))
    except OSError:
        await shared.dispose()
        pytest.skip("Postgres not reachable")
    if exists is None:
        await shared.dispose()
        pytest.skip("database not migrated")
    os.environ["IGS_DB_APP_ROLE"] = "igs_app"  # RLS applies even though we connect as owner
    yield engine
    os.environ.pop("IGS_DB_APP_ROLE", None)
    await shared.dispose()


async def _seed_tenant(engine: AsyncEngine, slug: str) -> dict[str, UUID]:
    ids = {k: uuid4() for k in ("tenant", "user", "contact", "lead", "trip", "account", "sh", "ix")}
    stmts = [
        ("insert into tenants (id, slug, name) values (:tenant, :slug, :label)", {}),
        (
            "insert into users (id, tenant_id, email, name, role) "
            "values (:user, :tenant, :email, 'Ops', 'ops')",
            {},
        ),
        (
            "insert into accounts (id, tenant_id, name, kind, country, status, health, "
            "sport_programs) values (:account, :tenant, 'Lakeshore University', 'university', "
            "'USA', 'active', 'amber', '{womens_soccer}')",
            {},
        ),
        (
            "insert into contacts (id, tenant_id, name, organization, account_id) "
            "values (:contact, :tenant, 'Dana Whitfield', 'Lakeshore University', :account)",
            {},
        ),
        (
            "insert into leads (id, tenant_id, contact_id, account_id, sport, gender, age_group, "
            "level_score, group_size, destination_country, travel_start, duration_days, status, "
            "source) values (:lead, :tenant, :contact, :account, 'soccer', 'women', 'college', 7, "
            "24, 'Argentina', '2027-03-07', 10, 'proposal_sent', 'chat')",
            {},
        ),
        (
            "insert into trips (id, tenant_id, lead_id, account_id, code, title, city, country, "
            "start_date, end_date, status, price_per_person_usd, summary) values (:trip, :tenant, "
            ":lead, :account, 'IGS-2711', 'Lakeshore BA 2027', 'Buenos Aires', 'Argentina', "
            "'2027-03-07', '2027-03-16', 'proposed', 2890, 'Women''s soccer tour')",
            {},
        ),
        (
            "insert into trip_items (id, tenant_id, trip_id, day, slot, kind, title, status) "
            "values "
            "(gen_random_uuid(), :tenant, :trip, 3, 'afternoon', 'match', 'vs Belgrano', "
            "'pending'), (gen_random_uuid(), :tenant, :trip, 3, 'morning', 'training', "
            "'Training', 'confirmed'), (gen_random_uuid(), :tenant, :trip, 1, 'evening', "
            "'arrival', 'Arrival', 'confirmed')",
            {},
        ),
        (
            "insert into stakeholders (id, tenant_id, account_id, name, role, influence, "
            "sentiment, preferred_channel) values (:sh, :tenant, :account, 'Dana Whitfield', "
            "'coach', 5, 'positive', 'email')",
            {},
        ),
        (
            "insert into interactions (id, tenant_id, account_id, stakeholder_id, channel, "
            "direction, occurred_at, subject, body) values (:ix, :tenant, :account, :sh, 'email', "
            "'inbound', now(), 'Budget', 'We can do up to 3000 per player.')",
            {},
        ),
        (
            "insert into account_facts (id, tenant_id, account_id, kind, statement, confidence, "
            "source_interaction_id, valid_from) values (gen_random_uuid(), :tenant, :account, "
            "'budget', 'Budget up to $3,000 per player', 0.9, :ix, now())",
            {},
        ),
        (
            "insert into api_keys (id, tenant_id, name, prefix, hash, scopes, created_by) values "
            "(gen_random_uuid(), :tenant, 'mcp', 'igs_', :hash, '{trips:read}', :user)",
            {"hash": hash_api_key(f"igs_{slug}")},
        ),
    ]
    async with engine.begin() as conn:
        for sql, extra in stmts:
            await conn.execute(
                text(sql),
                {**ids, "slug": slug, "label": slug, "email": f"{slug}@x.test", **extra},
            )
    return ids


@pytest.fixture(scope="module")
async def tenants(engine: AsyncEngine) -> dict[str, dict[str, UUID]]:
    suffix = uuid4().hex[:8]
    return {
        "a": await _seed_tenant(engine, f"a-{suffix}"),
        "b": await _seed_tenant(engine, f"b-{suffix}"),
    }


async def test_trips_list_and_detail(engine: AsyncEngine, tenants) -> None:
    trips = SqlTrips(shared.session_scope)
    a = tenants["a"]
    rows = await trips.list(a["tenant"], status=None, from_date=None, after=None, limit=10)
    assert [r.id for r in rows] == [a["trip"]]
    assert rows[0].team.organization == "Lakeshore University"
    assert rows[0].code == "IGS-2711"

    detail = await trips.get(a["tenant"], a["trip"])
    assert detail is not None
    assert [(i.day, i.slot) for i in detail.items] == [
        (1, "evening"),
        (3, "morning"),
        (3, "afternoon"),
    ]
    after = (date(2027, 3, 7), a["trip"])
    assert await trips.list(a["tenant"], status=None, from_date=None, after=after, limit=10) == []


async def test_rls_blocks_cross_tenant_reads(engine: AsyncEngine, tenants) -> None:
    trips, accounts = SqlTrips(shared.session_scope), SqlAccounts(shared.session_scope)
    a, b = tenants["a"], tenants["b"]
    assert await trips.get(b["tenant"], a["trip"]) is None
    assert await accounts.get(b["tenant"], a["account"]) is None


async def test_account_360(engine: AsyncEngine, tenants) -> None:
    a = tenants["a"]
    detail = await SqlAccounts(shared.session_scope).get(a["tenant"], a["account"])
    assert detail is not None
    assert detail.sport_programs == ["womens_soccer"]
    assert detail.stakeholders[0].preferred_channel == "email"
    assert detail.facts[0].kind == "budget"
    assert detail.facts[0].source_interaction_id == a["ix"]
    assert detail.recent_interactions[0].subject == "Budget"


async def test_directory(engine: AsyncEngine, tenants) -> None:
    directory = SqlDirectory(engine)
    await directory.ping()
    slug = await _slug(engine, tenants["a"]["tenant"])
    assert await directory.tenant_id_by_slug(slug) == tenants["a"]["tenant"]
    principal = await directory.principal_for_api_key(hash_api_key(f"igs_{slug}"))
    assert principal is not None
    assert principal.tenant_id == tenants["a"]["tenant"]
    assert principal.role == "ops"
    assert await directory.principal_for_api_key("nope") is None


async def test_app_end_to_end(engine: AsyncEngine, tenants) -> None:
    slug = await _slug(engine, tenants["a"]["tenant"])
    app = create_app(Settings(environment="test", database_url=URL, demo_tenant_slug=slug))
    transport = httpx.ASGITransport(app=app)
    async with (
        app.router.lifespan_context(app),
        httpx.AsyncClient(transport=transport, base_url="http://t") as client,
    ):
        assert (await client.get("/readyz")).status_code == 200
        r = await client.get("/v1/trips")
        assert [t["id"] for t in r.json()["items"]] == [str(tenants["a"]["trip"])]
        acc = await client.get(f"/v1/accounts/{tenants['a']['account']}")
        assert acc.status_code == 200
        # Detail health is recomputed by the deterministic rules (no open risks here → green);
    # the stored "amber" is only the list view's cached label.
    assert acc.json()["health"] == "green"
    assert isinstance(acc.json()["health_reasons"], list)


async def _slug(engine: AsyncEngine, tenant_id: UUID) -> str:
    async with engine.connect() as conn:
        return await conn.scalar(text("select slug from tenants where id = :id"), {"id": tenant_id})
