"""Entry points used by the worker, the copilot/MCP tool and Account 360."""

from __future__ import annotations

from collections.abc import Iterable
from datetime import date
from typing import Any
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from igs_common.llm import LLMClient

from .inbox import enqueue_reminders
from .position import TripPosition, assess_trip
from .reminders import draft_reminder, group_reminders
from .repo import load_trip_plans
from .terms import DEFAULT_TERMS, PaymentTerms


async def payment_positions(
    session: AsyncSession,
    *,
    tenant_id: UUID,
    today: date,
    account_id: UUID | None = None,
    trip_id: UUID | None = None,
    terms: PaymentTerms = DEFAULT_TERMS,
) -> list[TripPosition]:
    plans = await load_trip_plans(
        session, tenant_id=tenant_id, today=today, account_id=account_id, trip_id=trip_id
    )
    return [assess_trip(p, today=today, terms=terms) for p in plans]


def risk_rows(
    positions: Iterable[TripPosition], *, within_days: int = 14, terms: PaymentTerms = DEFAULT_TERMS
) -> list[dict[str, Any]]:
    """Overdue lines plus those due within ``within_days``, worst first (tool/API shape).

    No people in it: the copilot and MCP clients see seats, invoices and amounts.
    """
    rows: list[dict[str, Any]] = []
    for pos in positions:
        plan = pos.plan
        for line in pos.open_lines:
            if not line.stage.is_overdue and line.days > within_days:
                continue
            rows.append(
                {
                    "trip_id": str(plan.trip_id),
                    "trip_code": plan.code,
                    "account_id": str(plan.account_id) if plan.account_id else None,
                    "account": plan.account_name,
                    "departure": plan.start_date.isoformat(),
                    "kind": line.kind.value,
                    "due": line.due.isoformat(),
                    "days": line.days,
                    "stage": line.stage.value,
                    "seats": line.seats,
                    "outstanding_usd": line.outstanding_usd,
                    # Per missed payment under the terms: per seat, or one per invoice.
                    "late_fee_usd": terms.late_fee_usd * (line.seats or 1) if line.days < 0 else 0,
                    "invoice_ref": line.ref,
                    "recipient": plan.to.name if plan.to else None,
                }
            )
    return sorted(rows, key=lambda r: (r["days"], -r["outstanding_usd"]))


async def queue_reminders(
    session: AsyncSession,
    *,
    tenant_id: UUID,
    today: date,
    llm: LLMClient | None,
    terms: PaymentTerms = DEFAULT_TERMS,
) -> dict[str, int]:
    """Daily run: scan → group → draft (LLM tone, code facts) → approvals. Idempotent."""
    positions = await payment_positions(session, tenant_id=tenant_id, today=today, terms=terms)
    groups = group_reminders(positions, today=today)
    drafts = [(g, await draft_reminder(llm, g)) for g in groups]
    created = await enqueue_reminders(session, tenant_id=tenant_id, drafts=drafts)
    return {
        "trips": len(positions),
        "reminders": len(groups),
        "approvals_created": len(created),
        "template_fallbacks": sum(d.source == "template" for _, d in drafts),
    }
