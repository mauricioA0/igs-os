"""Dependencies for the write side (approvals, flows, executions, events).

The read routers go through ``Repositories``; the write side needs a tenant-scoped session,
the Temporal gateway and the notification hub, all set on ``app.state`` by the lifespan.
"""

from collections.abc import Callable
from contextlib import AbstractAsyncContextManager
from typing import Annotated
from uuid import UUID

from fastapi import Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession

from igs_core.deps import CurrentPrincipal
from igs_core.errors import ProblemError
from igs_core.events.listen import NotificationHub
from igs_core.repositories import Principal
from igs_core.temporal import WorkflowGateway

SessionFactory = Callable[[UUID], AbstractAsyncContextManager[AsyncSession]]

WRITER_ROLES = frozenset({"owner", "ops"})


def get_session_factory(request: Request) -> SessionFactory:
    factory = getattr(request.app.state, "tenant_session", None)
    if factory is None:
        raise ProblemError(503, "storage-unavailable", "This deployment has no database.")
    return factory


def get_gateway(request: Request) -> WorkflowGateway:
    gateway = getattr(request.app.state, "workflows", None)
    if gateway is None:
        raise ProblemError(503, "workflows-unavailable", "Temporal is not configured.")
    return gateway


def get_hub(request: Request) -> NotificationHub | None:
    return getattr(request.app.state, "hub", None)


def require_writer(principal: CurrentPrincipal) -> Principal:
    """Owners and ops may change state. The public demo and viewers are read-only."""
    if principal.kind == "demo":
        raise ProblemError(403, "read-only-demo", "The public demo is read-only.")
    if principal.role not in WRITER_ROLES:
        raise ProblemError(403, "forbidden", "Your role cannot perform this action.")
    return principal


def request_id(request: Request) -> str | None:
    return getattr(request.state, "request_id", None)


Sessions = Annotated[SessionFactory, Depends(get_session_factory)]
Workflows = Annotated[WorkflowGateway, Depends(get_gateway)]
Hub = Annotated[NotificationHub | None, Depends(get_hub)]
Writer = Annotated[Principal, Depends(require_writer)]
RequestId = Annotated[str | None, Depends(request_id)]
