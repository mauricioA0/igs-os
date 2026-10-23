"""Seed loads every fixture and is idempotent.

Needs the local Postgres (`docker compose up -d db`).
"""

import asyncio
import os
import uuid
from collections.abc import AsyncIterator, Iterator
from datetime import date
from pathlib import Path

import asyncpg
import pytest
import yaml
from alembic import command
from alembic.config import Config
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker
from sqlalchemy.pool import NullPool

from igs_common.db import session_scope
from igs_common.db.rls import APP_ROLE
from igs_common.db.session import create_engine
from igs_common.readiness.store import set_document_status, trip_readiness
from igs_common.seed import FIXTURES_DIR, fixture_id, load, reset_demo

ADMIN_URL = os.environ.get("IGS_TEST_ADMIN_URL", "postgresql://igs:igs@localhost:5433/igs")
TEST_DB = "igs_test_p3"
ALEMBIC_INI = Path(__file__).resolve().parents[2] / "alembic.ini"
TABLES = (
    "tenants users providers opponents experiences documents accounts contacts leads trips "
    "trip_items stakeholders interactions account_facts flows flow_versions flow_triggers "
    "flow_executions flow_node_runs approvals audit_log travelers traveler_documents"
).split()


def _test_url() -> str:
    return ADMIN_URL.rsplit("/", 1)[0] + f"/{TEST_DB}"


async def _recreate_database() -> None:
    conn = await asyncpg.connect(ADMIN_URL)
    try:
        await conn.execute(f'DROP DATABASE IF EXISTS "{TEST_DB}" WITH (FORCE)')
        await conn.execute(f'CREATE DATABASE "{TEST_DB}"')
    finally:
        await conn.close()


@pytest.fixture(scope="module")
def migrated_url() -> Iterator[str]:
    try:
        asyncio.run(_recreate_database())
    except (OSError, asyncpg.PostgresError) as exc:  # pragma: no cover - env dependent
        pytest.skip(f"local Postgres not available: {exc}")
    cfg = Config(str(ALEMBIC_INI))
    cfg.cmd_opts = type("Opts", (), {"x": [f"url={_test_url()}"]})()  # type: ignore[assignment]
    command.upgrade(cfg, "head")
    yield _test_url()


@pytest.fixture
async def engine(migrated_url: str) -> AsyncIterator[AsyncEngine]:
    eng = create_engine(migrated_url, poolclass=NullPool)
    yield eng
    await eng.dispose()


async def _seed(engine: AsyncEngine) -> None:
    async with async_sessionmaker(engine)() as session, session.begin():
        await load(session)


async def _counts(session: AsyncSession) -> dict[str, int]:
    counts = {}
    for table in TABLES:  # fixed allowlist above, not user input
        query = text(f"SELECT count(*) FROM {table}")  # noqa: S608
        counts[table] = (await session.execute(query)).scalar_one()
    return counts


async def test_seed_is_idempotent(engine: AsyncEngine) -> None:
    await _seed(engine)
    async with async_sessionmaker(engine)() as session:
        first = await _counts(session)
    await _seed(engine)
    async with async_sessionmaker(engine)() as session:
        second = await _counts(session)

    assert first == second
    accounts = yaml.safe_load((FIXTURES_DIR / "accounts.yaml").read_text())["accounts"]
    assert first["accounts"] == len(accounts) == 6
    assert first["interactions"] == sum(len(a["interactions"]) for a in accounts)
    assert first["trips"] == 7
    assert first["flows"] == first["flow_versions"] == first["flow_triggers"] == 3
    assert first["flow_executions"] == 3 and first["flow_node_runs"] == 8 + 12 + 5


async def test_seed_links_account_360(engine: AsyncEngine) -> None:
    await _seed(engine)
    lakeshore = fixture_id("igs", "account", "acc-lakeshore")
    async with async_sessionmaker(engine)() as session:
        row = (
            await session.execute(
                text(
                    "SELECT a.health, count(DISTINCT i.id), count(DISTINCT s.id), "
                    "count(DISTINCT t.id) FROM accounts a "
                    "JOIN interactions i ON i.account_id = a.id "
                    "JOIN stakeholders s ON s.account_id = a.id "
                    "JOIN trips t ON t.account_id = a.id WHERE a.id = :id GROUP BY a.health"
                ),
                {"id": lakeshore},
            )
        ).one()
        decider = (
            await session.execute(
                text(
                    "SELECT s.name FROM account_facts f "
                    "JOIN interactions i ON i.id = f.source_interaction_id "
                    "JOIN stakeholders s ON s.id = i.stakeholder_id "
                    "WHERE f.id = :id"
                ),
                {"id": fixture_id("igs", "account_fact", "fact-lak-decider")},
            )
        ).scalar_one()
    assert tuple(row) == ("red", 12, 6, 1)
    assert decider == "Robert Haines"


def test_golden_questions_cite_existing_interactions() -> None:
    accounts = yaml.safe_load((FIXTURES_DIR / "accounts.yaml").read_text())["accounts"]
    owner = {i["key"]: a["key"] for a in accounts for i in a["interactions"]}
    questions = yaml.safe_load((FIXTURES_DIR / "account-qa.yaml").read_text())["questions"]
    assert len(questions) == 40
    for q in questions:
        assert q["sources"], q["id"]
        for source in q["sources"]:
            assert source in owner, (q["id"], source)
            if q["account"]:
                assert owner[source] == q["account"], (q["id"], source)


async def test_lakeshore_story_is_coherent(engine: AsyncEngine) -> None:
    """One story on every surface: March 2027 proposal waiting for ops on a parked execution."""
    await _seed(engine)
    trip = fixture_id("igs", "trip", "t-2711")
    execution = fixture_id("igs", "execution", "ex-lak-inbound")
    async with async_sessionmaker(engine)() as session:
        t = (
            await session.execute(
                text("SELECT status, start_date::text, end_date::text FROM trips WHERE id = :id"),
                {"id": trip},
            )
        ).one()
        lead = (
            await session.execute(
                text("SELECT status::text FROM leads WHERE id = :id"),
                {"id": fixture_id("igs", "lead", "l-508")},
            )
        ).scalar_one()
        approval = (
            await session.execute(
                text(
                    "SELECT status::text, execution_id, node_id, subject_id, "
                    "proposed_action->>'action', proposed_action->'params'->>'tripId', "
                    "payload_hash FROM approvals WHERE id = :id"
                ),
                {"id": fixture_id("igs", "approval", "a-9003")},
            )
        ).one()
        ex = (
            await session.execute(
                text(
                    "SELECT e.status::text, e.vars->>'trip_id', r.node_id, r.status::text "
                    "FROM flow_executions e JOIN flow_node_runs r ON r.execution_id = e.id "
                    "WHERE e.id = :id ORDER BY r.started_at DESC, r.id LIMIT 1"
                ),
                {"id": execution},
            )
        ).one()
        risk = (
            await session.execute(
                text("SELECT severity::text, status::text FROM account_facts WHERE id = :id"),
                {"id": fixture_id("igs", "account_fact", "fact-lak-hold-overdue")},
            )
        ).one()
    assert tuple(t) == ("proposed", "2027-03-06", "2027-03-15")
    assert lead == "qualified"
    status, execution_id, node_id, subject_id, action, trip_param, digest = approval
    assert (status, execution_id, node_id, subject_id) == ("pending", execution, "ops_review", trip)
    assert (action, trip_param) == ("send_proposal", str(trip)) and digest.startswith("sha256:")
    assert tuple(ex) == ("waiting", str(trip), "ops_review", "waiting")
    assert tuple(risk) == ("high", "open")  # what makes Lakeshore red


async def test_reset_demo_restores_fixture_state(engine: AsyncEngine) -> None:
    await _seed(engine)
    approval = fixture_id("igs", "approval", "a-9003")
    async with async_sessionmaker(engine)() as session:
        baseline = await _counts(session)
    # A visitor approves the proposal and the agent creates a new lead.
    async with async_sessionmaker(engine)() as session, session.begin():
        tenant = (await session.execute(text("SELECT id FROM tenants WHERE slug = 'igs'"))).scalar()
        await session.execute(
            text("UPDATE approvals SET status = 'approved', comment = 'ok' WHERE id = :id"),
            {"id": approval},
        )
        await session.execute(
            text(
                "INSERT INTO leads (id, tenant_id, sport, gender, age_group, level_score, "
                "group_size, destination_country, travel_start, duration_days, status, source) "
                "VALUES (gen_random_uuid(), :t, 'soccer', 'men', 'U17', 6, 20, 'Brazil', "
                "'2027-06-01', 8, 'new', 'chat')"
            ),
            {"t": tenant},
        )
    for _ in range(2):  # idempotent
        async with async_sessionmaker(engine)() as session, session.begin():
            await reset_demo(session)
    async with async_sessionmaker(engine)() as session:
        after = await _counts(session)
        row = (
            await session.execute(
                text("SELECT status::text, comment FROM approvals WHERE id = :id"),
                {"id": approval},
            )
        ).one()
    assert {k: v for k, v in after.items() if k != "audit_log"} == {
        k: v for k, v in baseline.items() if k != "audit_log"
    }
    assert tuple(row) == ("pending", None)


async def test_reset_refuses_other_tenants(engine: AsyncEngine) -> None:
    async with async_sessionmaker(engine)() as session:
        with pytest.raises(ValueError, match="non-demo"):
            await reset_demo(session, tenant_slug="acme")


async def _tenant(engine: AsyncEngine) -> uuid.UUID:
    async with async_sessionmaker(engine)() as session:
        return (
            await session.execute(text("SELECT id FROM tenants WHERE slug = 'igs'"))
        ).scalar_one()


async def test_rio_roster_readiness_tells_the_story(engine: AsyncEngine) -> None:
    await _seed(engine)
    tenant = await _tenant(engine)
    trip = fixture_id("igs", "trip", "t-2715")
    async with session_scope(tenant, engine=engine, role=APP_ROLE) as s:
        report = await trip_readiness(s, trip, today=date(2026, 10, 22))
    assert report is not None
    assert report["trip"]["code"] == "IGS-2715"
    assert report["trip"]["destination"] == "BR"
    assert report["travelers"] == 22
    assert report["ready"] is False
    evisa = report["by_requirement"]["br_evisa"]
    assert evisa == {"done": 18, "open": 4, "overdue": 4}  # T-60 passed on Oct 6
    coach = next(p for p in report["people"] if p["full_name"] == "Paul Lindgren")
    passport = next(i for i in coach["items"] if i["requirement"] == "passport")
    assert passport["state"] == "invalid"  # expires Dec 11, the trip ends Dec 14
    waived = next(p for p in report["people"] if p["full_name"] == "Noah Brennan")
    consent = next(i for i in waived["items"] if i["requirement"] == "parental_consent")
    assert consent["state"] == "waived"


async def test_document_status_update_is_tenant_scoped_and_reset(engine: AsyncEngine) -> None:
    await _seed(engine)
    tenant = await _tenant(engine)
    player = fixture_id("igs", "traveler", "t-2715-p19")
    async with session_scope(tenant, engine=engine, role=APP_ROLE) as s:
        row = await set_document_status(
            s, tenant, player, "br_evisa", status="verified", valid_until=date(2036, 1, 1)
        )
    assert row is not None and row["status"] == "verified"
    async with session_scope(tenant, engine=engine, role=APP_ROLE) as s:
        again = await set_document_status(s, tenant, player, "br_evisa", status="verified")
    assert again is not None and again["valid_until"] == "2036-01-01"  # dates kept
    other = uuid.uuid4()
    async with session_scope(other, engine=engine, role=APP_ROLE) as s:
        assert await set_document_status(s, other, player, "br_evisa", status="missing") is None
    with pytest.raises(ValueError, match="unknown requirement"):
        async with session_scope(tenant, engine=engine, role=APP_ROLE) as s:
            await set_document_status(s, tenant, player, "selfie", status="verified")
    async with async_sessionmaker(engine)() as session, session.begin():
        await reset_demo(session)
    async with async_sessionmaker(engine)() as session:
        status = (
            await session.execute(
                text(
                    "SELECT status FROM traveler_documents "
                    "WHERE traveler_id = :t AND requirement = 'br_evisa'"
                ),
                {"t": player},
            )
        ).scalar_one()
    assert status == "missing"
