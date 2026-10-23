from datetime import datetime
from typing import Annotated
from uuid import UUID
from zoneinfo import ZoneInfo

import structlog
from fastapi import APIRouter, Query

from igs_common.accounts.health import compute_health
from igs_common.accounts.snapshot import load_snapshot
from igs_core import db
from igs_core.deps import AppSettings, CurrentPrincipal, Repos
from igs_core.errors import ProblemError
from igs_core.schemas.accounts import AccountDetail, AccountStatus, AccountSummary, Health
from igs_core.schemas.common import Page, decode_cursor, encode_cursor, parse_cursor_value

router = APIRouter(prefix="/accounts", tags=["accounts"])
log = structlog.get_logger("igs_core.accounts")
# Health rules reason about "today" in the ops team's calendar.
OPS_TZ = ZoneInfo("America/Argentina/Buenos_Aires")


@router.get("", response_model=Page[AccountSummary], summary="List client accounts")
async def list_accounts(
    principal: CurrentPrincipal,
    repos: Repos,
    settings: AppSettings,
    status: AccountStatus | None = None,
    health: Health | None = None,
    cursor: str | None = None,
    limit: Annotated[int | None, Query(ge=1, le=200)] = None,
) -> Page[AccountSummary]:
    size = min(limit or settings.page_size_default, settings.page_size_max)
    after = None
    if cursor:
        name, account_id = decode_cursor(cursor, 2)
        after = (name, parse_cursor_value(UUID, account_id))
    rows = await repos.accounts.list(
        principal.tenant_id, status=status, health=health, after=after, limit=size + 1
    )
    page, more = rows[:size], len(rows) > size
    next_cursor = encode_cursor(page[-1].name, page[-1].id) if more else None
    return Page[AccountSummary](items=page, next_cursor=next_cursor)


@router.get(
    "/{account_id}",
    response_model=AccountDetail,
    summary="Account 360: stakeholders, current facts with sources, recent interactions",
)
async def get_account(account_id: UUID, principal: CurrentPrincipal, repos: Repos) -> AccountDetail:
    account = await repos.accounts.get(principal.tenant_id, account_id)
    if account is None:
        raise ProblemError(404, "not-found", "Account not found.")
    try:
        async with db.tenant_session(principal.tenant_id) as session:
            snapshot = await load_snapshot(
                session, tenant_id=principal.tenant_id, account_id=account_id
            )
        if snapshot is not None:
            result = compute_health(snapshot, today=datetime.now(OPS_TZ).date())
            account = account.model_copy(
                update={"health": result.health, "health_reasons": list(result.reasons)}
            )
    except Exception:  # the stored health still renders; reasons are an enrichment
        log.warning("account_health_failed", account_id=str(account_id), exc_info=True)
    return account
