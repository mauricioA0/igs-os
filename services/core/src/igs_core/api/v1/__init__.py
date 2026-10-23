from typing import Literal

from fastapi import APIRouter
from pydantic import BaseModel

from igs_core.api.v1 import (
    accounts,
    approvals,
    digest,
    events,
    executions,
    flows,
    imports,
    intake,
    leads,
    trips,
)
from igs_core.deps import CurrentPrincipal
from igs_core.errors import PROBLEM_RESPONSES


class Me(BaseModel):
    kind: Literal["demo", "api_key", "user"]
    tenant_id: str
    role: str
    subject: str
    scopes: list[str]


router = APIRouter(prefix="/v1", responses=PROBLEM_RESPONSES)


@router.get("/me", response_model=Me, tags=["auth"], summary="Who is calling")
async def me(principal: CurrentPrincipal) -> Me:
    return Me(
        kind=principal.kind,
        tenant_id=str(principal.tenant_id),
        role=principal.role,
        subject=principal.subject,
        scopes=sorted(principal.scopes),
    )


router.include_router(trips.router)
router.include_router(accounts.router)
router.include_router(leads.router)
router.include_router(intake.router)
router.include_router(approvals.router)
router.include_router(flows.router)
router.include_router(executions.router)
router.include_router(events.router)
router.include_router(imports.router)
router.include_router(digest.router)
