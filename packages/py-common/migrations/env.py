"""Alembic environment (async, asyncpg).

URL precedence: `-x url=...` > $IGS_DATABASE_URL > $DATABASE_URL.
The connecting user is the **migration role**: it owns the tables (see igs_common.db.rls).
"""

import asyncio
import os

from alembic import context
from sqlalchemy.engine import Connection

import igs_common.db.models  # noqa: F401  (registers every table)
from igs_common.db.base import Base
from igs_common.db.session import create_engine, normalize_url

config = context.config
target_metadata = Base.metadata


def _url() -> str:
    url = (
        context.get_x_argument(as_dictionary=True).get("url")
        or os.environ.get("IGS_DATABASE_URL")
        or os.environ.get("DATABASE_URL")
    )
    if not url:
        raise RuntimeError("Set DATABASE_URL or pass -x url=postgresql://...")
    return normalize_url(url)


def run_migrations_offline() -> None:
    context.configure(
        url=_url(),
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        compare_type=True,
    )
    with context.begin_transaction():
        context.run_migrations()


def _run(connection: Connection) -> None:
    context.configure(connection=connection, target_metadata=target_metadata, compare_type=True)
    with context.begin_transaction():
        context.run_migrations()


async def run_migrations_online() -> None:
    engine = create_engine(_url())
    async with engine.connect() as connection:
        await connection.run_sync(_run)
    await engine.dispose()


if context.is_offline_mode():
    run_migrations_offline()
else:
    asyncio.run(run_migrations_online())
