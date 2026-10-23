"""The digest over a migrated + freshly seeded Postgres (`docker compose up -d db`).

The seed dates are relative to today (igs_common.seed.anchor), so "now" is the real clock.
"""

import asyncio
import os
from collections.abc import AsyncIterator, Iterator
from contextlib import asynccontextmanager
from datetime import UTC, datetime
from pathlib import Path
from uuid import UUID

import asyncpg
import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker
from sqlalchemy.pool import NullPool

from igs_common.db.enums import ApprovalStatus
from igs_common.db.models import Approval
from igs_common.db.session import create_engine, session_scope
from igs_common.digest import (
    allowed_numbers,
    check_numbers,
    generate_digest,
    template_summary,
)
from igs_common.seed import fixture_id, load

ADMIN_URL = os.environ.get("IGS_TEST_ADMIN_URL", "postgresql://igs:igs@localhost:5433/igs")
TEST_DB = "igs_test_d7"
ALEMBIC_INI = Path(__file__).resolve().parents[2] / "alembic.ini"
TENANT = fixture_id("igs", "tenant", "igs")
LAKESHORE = fixture_id("igs", "account", "acc-lakeshore")


def _test_url() -> str:
    return ADMIN_URL.rsplit("/", 1)[0] + f"/{TEST_DB}"


async def _recreate_database() -> None:
    conn = await asyncpg.connect(ADMIN_URL)
    try:
        await conn.execute(f'DROP DATABASE IF EXISTS "{TEST_DB}" WITH (FORCE)')
        await conn.execute(f'CREATE DATABASE "{TEST_DB}"')
    finally:
        await conn.close()


async def _seed(url: str) -> None:
    engine = create_engine(url, poolclass=NullPool)
    try:
        async with async_sessionmaker(engine)() as session, session.begin():
            await load(session)
    finally:
        await engine.dispose()


@pytest.fixture(scope="module")
def seeded_url() -> Iterator[str]:
    try:
        asyncio.run(_recreate_database())
    except (OSError, asyncpg.PostgresError) as exc:  # pragma: no cover - env dependent
        pytest.skip(f"local Postgres not available: {exc}")
    cfg = Config(str(ALEMBIC_INI))
    cfg.cmd_opts = type("Opts", (), {"x": [f"url={_test_url()}"]})()  # type: ignore[assignment]
    command.upgrade(cfg, "head")
    asyncio.run(_seed(_test_url()))
    yield _test_url()


@pytest.fixture
async def engine(seeded_url: str) -> AsyncIterator[AsyncEngine]:
    eng = create_engine(seeded_url, poolclass=NullPool)
    yield eng
    await eng.dispose()


def _factory(engine: AsyncEngine):  # noqa: ANN202
    @asynccontextmanager
    async def factory(tenant_id: UUID) -> AsyncIterator[AsyncSession]:
        async with session_scope(tenant_id, engine=engine, role="igs_app") as session:
            yield session

    return factory


async def test_seeded_digest_tells_the_lakeshore_story(engine: AsyncEngine) -> None:
    now = datetime.now(UTC)
    digest = await generate_digest(_factory(engine), tenant_id=TENANT, llm=None, now=now)
    facts = digest.facts

    top = facts.risks[0]
    assert (top.subject_id, top.level) == (LAKESHORE, "red")
    assert "enrollment fees" in top.reason
    assert top.next_action.startswith("Decidir la aprobación")

    # Same number as the inbox badge (effective pending).
    async with session_scope(TENANT, engine=engine) as session:
        pending = await session.scalar(
            select(func.count())
            .select_from(Approval)
            .where(
                Approval.status == ApprovalStatus.PENDING,
                (Approval.expires_at.is_(None)) | (Approval.expires_at > now),
            )
        )
    assert facts.counts.approvals_pending == pending

    assert any(p.name == "Lakeshore University" for p in facts.payments)
    assert check_numbers(template_summary(facts), allowed_numbers(facts.to_json())).ok
    assert "Hoy en</span>" in digest.html() and digest.text().startswith("IGS OS")


async def test_another_tenant_sees_nothing(engine: AsyncEngine) -> None:
    digest = await generate_digest(
        _factory(engine), tenant_id=UUID(int=42), llm=None, now=datetime.now(UTC)
    )
    assert digest.facts.risks == () and digest.facts.counts.approvals_pending == 0
