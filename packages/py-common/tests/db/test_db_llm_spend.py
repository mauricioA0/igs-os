"""Migration 0005: the daily spend table is shared across processes and writable by igs_app."""

from datetime import date
from decimal import Decimal

import asyncpg
from sqlalchemy.ext.asyncio import AsyncEngine

from igs_common.llm.budget import PgSpendStore


async def test_spend_accumulates_per_day(engine: AsyncEngine) -> None:
    store = PgSpendStore(engine)
    day = date(2031, 1, 2)
    assert await store.spent(day) == 0
    await store.add(day, Decimal("0.25"))
    await store.add(day, Decimal("0.50"))
    assert await store.spent(day) == Decimal("0.75")
    assert await store.spent(date(2031, 1, 3)) == 0


async def test_app_role_can_upsert(migrated: str) -> None:
    conn = await asyncpg.connect(migrated)
    try:
        async with conn.transaction():
            await conn.execute("SET LOCAL ROLE igs_app")
            for _ in range(2):
                await conn.execute(
                    "INSERT INTO llm_spend_daily (day, cost_usd, calls) VALUES ($1, 1, 1) "
                    "ON CONFLICT (day) DO UPDATE SET calls = llm_spend_daily.calls + 1",
                    date(2031, 2, 1),
                )
            calls = await conn.fetchval(
                "SELECT calls FROM llm_spend_daily WHERE day = $1", date(2031, 2, 1)
            )
        assert calls == 2
    finally:
        await conn.close()
