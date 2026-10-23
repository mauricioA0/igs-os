"""Test support: throwaway Postgres databases migrated to head.

Integration tests each own a database (``igs_test_<name>``) so suites can run in parallel and
in CI without any manual setup. Requires a reachable Postgres (``docker compose up -d db``).
"""

from __future__ import annotations

import asyncio
import os
from pathlib import Path

import asyncpg
from alembic import command
from alembic.config import Config

ADMIN_URL = os.environ.get("IGS_TEST_ADMIN_URL", "postgresql://igs:igs@localhost:5433/igs")
ALEMBIC_INI = Path(__file__).resolve().parents[2] / "alembic.ini"


class DatabaseUnavailableError(RuntimeError):
    """Postgres can't be reached; callers usually skip."""


def database_url(name: str, *, driver: str = "postgresql") -> str:
    base = ADMIN_URL.split("://", 1)[1].rsplit("/", 1)[0]
    return f"{driver}://{base}/{name}"


async def _recreate(name: str) -> None:
    conn = await asyncpg.connect(ADMIN_URL)
    try:
        await conn.execute(f'DROP DATABASE IF EXISTS "{name}" WITH (FORCE)')
        await conn.execute(f'CREATE DATABASE "{name}"')
    finally:
        await conn.close()


def prepare_database(name: str) -> str:
    """Drop, create and migrate ``name`` to head. Call outside a running event loop."""
    if not name.startswith("igs_test_"):
        raise ValueError("test databases must be named igs_test_*")
    try:
        asyncio.run(_recreate(name))
    except (OSError, asyncpg.PostgresError) as exc:
        raise DatabaseUnavailableError(str(exc)) from exc
    cfg = Config(str(ALEMBIC_INI))
    cfg.cmd_opts = type("Opts", (), {"x": [f"url={database_url(name)}"]})()  # type: ignore[assignment]
    command.upgrade(cfg, "head")
    return database_url(name)
