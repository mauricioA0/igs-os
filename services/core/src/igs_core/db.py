"""The single seam between the API and ``igs_common.db``.

Everything the core service needs from the database layer goes through these functions,
so a change in the shared session API is a one-file fix here.
"""

from contextlib import AbstractAsyncContextManager
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession

from igs_common.db import session as shared


def open_engine(database_url: str) -> AsyncEngine:
    """Configure the process-wide engine that ``session_scope`` uses."""
    return shared.configure(database_url)


async def close_engine() -> None:
    await shared.dispose()


def tenant_session(tenant_id: UUID) -> AbstractAsyncContextManager[AsyncSession]:
    """One transaction with ``app.tenant_id`` set, so row-level security applies."""
    return shared.session_scope(tenant_id)
