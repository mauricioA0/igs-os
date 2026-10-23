"""DB test fixtures: a throwaway database per session, migrated with Alembic.

Needs the local Postgres (`docker compose up -d db`). Override with $IGS_TEST_ADMIN_URL.
"""

import asyncio
import os
from collections.abc import AsyncIterator, Iterator
from pathlib import Path

import asyncpg
import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy.ext.asyncio import AsyncEngine
from sqlalchemy.pool import NullPool

from igs_common.db.session import create_engine

ADMIN_URL = os.environ.get("IGS_TEST_ADMIN_URL", "postgresql://igs:igs@localhost:5433/igs")
TEST_DB = "igs_test_p1"
ALEMBIC_INI = Path(__file__).resolve().parents[2] / "alembic.ini"


def _test_url() -> str:
    return ADMIN_URL.rsplit("/", 1)[0] + f"/{TEST_DB}"


async def _recreate_database() -> None:
    conn = await asyncpg.connect(ADMIN_URL)
    try:
        await conn.execute(f'DROP DATABASE IF EXISTS "{TEST_DB}" WITH (FORCE)')
        await conn.execute(f'CREATE DATABASE "{TEST_DB}"')
    finally:
        await conn.close()


def alembic_config() -> Config:
    cfg = Config(str(ALEMBIC_INI))
    cfg.cmd_opts = type("Opts", (), {"x": [f"url={_test_url()}"]})()  # type: ignore[assignment]
    return cfg


@pytest.fixture(scope="session")
def db_url() -> Iterator[str]:
    try:
        asyncio.run(_recreate_database())
    except (OSError, asyncpg.PostgresError) as exc:  # pragma: no cover - env dependent
        pytest.skip(f"local Postgres not available: {exc}")
    yield _test_url()


@pytest.fixture(scope="session")
def alembic_cfg(db_url: str) -> Config:
    return alembic_config()


@pytest.fixture(scope="session")
def migrated(alembic_cfg: Config, db_url: str) -> str:
    command.upgrade(alembic_cfg, "head")
    return db_url


@pytest.fixture
async def engine(migrated: str) -> AsyncIterator[AsyncEngine]:
    eng = create_engine(migrated, poolclass=NullPool)
    yield eng
    await eng.dispose()
