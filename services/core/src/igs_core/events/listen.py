"""One Postgres LISTEN connection per process, fanned out to in-process waiters.

Used by the execution SSE stream (``igs_node_runs``, payload = execution id) and the outbox
dispatcher (``igs_outbox``). Listening is an optimization: every waiter also wakes up on a
timeout and re-reads the database, so a missed or unsupported NOTIFY only adds latency.
"""

import asyncio
import contextlib
from collections import defaultdict
from typing import Any

import structlog
from sqlalchemy.ext.asyncio import AsyncConnection, AsyncEngine

log = structlog.get_logger("igs_core.events.listen")


class NotificationHub:
    def __init__(self, engine: AsyncEngine, channels: tuple[str, ...]) -> None:
        self._engine = engine
        self._channels = channels
        self._conn: AsyncConnection | None = None
        self._waiters: dict[tuple[str, str | None], set[asyncio.Event]] = defaultdict(set)
        self._lock = asyncio.Lock()
        self._started = False

    async def start(self) -> None:
        async with self._lock:
            if self._started:
                return
            self._started = True
            try:
                self._conn = await self._engine.connect()
                raw: Any = (await self._conn.get_raw_connection()).driver_connection
                for channel in self._channels:
                    await raw.add_listener(channel, self._on_notify)
            except Exception:  # noqa: BLE001 - polling still works without LISTEN
                log.warning("listen_unavailable", channels=self._channels, exc_info=True)
                await self._close_conn()

    async def stop(self) -> None:
        async with self._lock:
            await self._close_conn()
            self._started = False

    async def _close_conn(self) -> None:
        if self._conn is not None:
            with contextlib.suppress(Exception):
                await self._conn.close()
        self._conn = None

    def _on_notify(self, _conn: object, _pid: int, channel: str, payload: str) -> None:
        for key in ((channel, payload), (channel, None)):
            for event in self._waiters.get(key, ()):
                event.set()

    async def wait(self, channel: str, key: str | None = None, wait_seconds: float = 2.0) -> bool:
        """Wait for a notification on ``channel`` (optionally for one payload). True if woken."""
        await self.start()
        event = asyncio.Event()
        self._waiters[(channel, key)].add(event)
        try:
            await asyncio.wait_for(event.wait(), wait_seconds)
            return True
        except TimeoutError:
            return False
        finally:
            waiters = self._waiters.get((channel, key))
            if waiters is not None:
                waiters.discard(event)
                if not waiters:
                    self._waiters.pop((channel, key), None)
