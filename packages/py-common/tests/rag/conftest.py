"""RAG test fixtures. The Postgres-backed tests use a throwaway DB `igs_test_w1`.

Migration 0002 adds embedding/sparse/tsv; `payload jsonb` is still pending there, so the fixture
adds every RAG column with IF NOT EXISTS and the store is tested against the contract either way.
"""

import asyncio
import os
from collections.abc import AsyncIterator, Iterator
from pathlib import Path

import asyncpg
import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine
from sqlalchemy.pool import NullPool

from igs_common.db.session import create_engine

ADMIN_URL = os.environ.get("IGS_TEST_ADMIN_URL", "postgresql://igs:igs@localhost:5433/igs")
TEST_DB = "igs_test_w1"
ALEMBIC_INI = Path(__file__).resolve().parents[2] / "alembic.ini"

RAG_COLUMNS = """
ALTER TABLE document_chunks ADD COLUMN IF NOT EXISTS embedding vector(1024);
ALTER TABLE document_chunks ADD COLUMN IF NOT EXISTS sparse jsonb;
ALTER TABLE document_chunks ADD COLUMN IF NOT EXISTS tsv tsvector
    GENERATED ALWAYS AS (to_tsvector('simple', content)) STORED;
ALTER TABLE document_chunks ADD COLUMN IF NOT EXISTS payload jsonb;
CREATE INDEX IF NOT EXISTS ix_document_chunks_embedding
    ON document_chunks USING hnsw (embedding vector_cosine_ops);
CREATE INDEX IF NOT EXISTS ix_document_chunks_tsv ON document_chunks USING gin (tsv);
"""


def _test_url() -> str:
    return ADMIN_URL.rsplit("/", 1)[0] + f"/{TEST_DB}"


async def _recreate_database() -> None:
    conn = await asyncpg.connect(ADMIN_URL)
    try:
        await conn.execute(f'DROP DATABASE IF EXISTS "{TEST_DB}" WITH (FORCE)')
        await conn.execute(f'CREATE DATABASE "{TEST_DB}"')
    finally:
        await conn.close()
    conn = await asyncpg.connect(_test_url())
    try:
        await conn.execute("CREATE EXTENSION IF NOT EXISTS vector")
    finally:
        await conn.close()


@pytest.fixture(scope="session")
def rag_db_url() -> Iterator[str]:
    try:
        asyncio.run(_recreate_database())
    except (OSError, asyncpg.PostgresError) as exc:  # pragma: no cover - env dependent
        pytest.skip(f"local Postgres not available: {exc}")
    cfg = Config(str(ALEMBIC_INI))
    cfg.cmd_opts = type("Opts", (), {"x": [f"url={_test_url()}"]})()  # type: ignore[assignment]
    command.upgrade(cfg, "head")
    yield _test_url()


@pytest.fixture
async def rag_engine(rag_db_url: str) -> AsyncIterator[AsyncEngine]:
    eng = create_engine(rag_db_url, poolclass=NullPool)
    async with eng.begin() as conn:
        for stmt in filter(None, (s.strip() for s in RAG_COLUMNS.split(";"))):
            await conn.execute(text(stmt))
    yield eng
    await eng.dispose()
