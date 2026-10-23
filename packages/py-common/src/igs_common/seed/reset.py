"""Reset the demo tenant to its fixture state: `python -m igs_common.seed --reset-demo`.

The public demo lets visitors approve, reject, chat and run flows. A reset removes what they
created and puts every fixture row back as seeded, so the guided tour always starts from the same
story. It is idempotent (reset twice = reset once) and scoped to one tenant.

Kept on purpose: `audit_log` (append-only by contract — decisions taken during a demo stay on
record) and the RAG chunks of fixture sources (re-indexing is a separate, explicit command).
"""

import uuid
from typing import Any

from sqlalchemy import bindparam, text
from sqlalchemy.ext.asyncio import AsyncSession

from igs_common.seed.load import SeedReport, _Fixtures, fixture_id, load

# Tenants a reset may touch. Resetting wipes visitor activity, so it must never reach a tenant
# holding real customers.
DEMO_TENANTS = frozenset({"igs"})

# Rows that only exist because someone used the demo. Order respects foreign keys.
_WIPE = (
    "traveler_documents",  # demo visitors mark documents; fixture statuses are reloaded
    "approvals",
    "flow_node_runs",
    "flow_executions",
    "outbox_events",
    "agent_steps",
    "agent_runs",
    "messages",
    "conversations",
    "account_briefs",
    "incidents",
)

# Nullable columns the app fills while the demo runs; the upsert leaves None alone, so clear them
# before reloading. `trip_items.time/alert/notes` are reloaded from fixtures right after.
_CLEAR = (
    "UPDATE trip_items SET requested_at = NULL, completed_at = NULL, result = NULL, "
    "alert = NULL, notes = NULL, time = NULL WHERE tenant_id = :tid",
    "UPDATE leads SET lost_reason = NULL WHERE tenant_id = :tid",
)


async def reset_demo(session: AsyncSession, *, tenant_slug: str = "igs") -> SeedReport:
    """Delete visitor-created rows of the demo tenant and re-seed it (caller's transaction)."""
    if tenant_slug not in DEMO_TENANTS:
        raise ValueError(f"refusing to reset non-demo tenant {tenant_slug!r}")
    tenant_id = (
        await session.execute(text("SELECT id FROM tenants WHERE slug = :s"), {"s": tenant_slug})
    ).scalar_one_or_none()
    if tenant_id is not None:
        params: dict[str, Any] = {"tid": tenant_id}
        keep = _fixture_ids(tenant_slug)
        # Leads, trips, interactions and facts created by agents or visitors (not fixtures).
        for table, kind in (
            ("account_facts", "account_fact"),
            ("interactions", "interaction"),
            ("trips", "trip"),
            ("leads", "lead"),
        ):
            stmt = text(
                f"DELETE FROM {table} WHERE tenant_id = :tid AND NOT (id = ANY(:keep))"  # noqa: S608 - fixed allowlist
            ).bindparams(bindparam("keep", value=keep[kind]))
            await session.execute(stmt, params)
        for table in _WIPE:
            await session.execute(
                text(f"DELETE FROM {table} WHERE tenant_id = :tid"),  # noqa: S608 - fixed allowlist
                params,
            )
        for sql in _CLEAR:
            await session.execute(text(sql), params)
    return await load(session, tenant_slug=tenant_slug)


def _fixture_ids(slug: str) -> dict[str, list[uuid.UUID]]:
    from igs_common.seed.load import FIXTURES_DIR, FLOW_EXAMPLES_DIR

    fx = _Fixtures(FIXTURES_DIR, FLOW_EXAMPLES_DIR)  # ids only: dates don't matter here
    ids: dict[str, list[uuid.UUID]] = {
        "lead": [fixture_id(slug, "lead", x["key"]) for x in fx.sales["leads"]],
        "trip": [fixture_id(slug, "trip", x["key"]) for x in fx.sales["trips"]],
        "interaction": [
            fixture_id(slug, "interaction", i["key"])
            for a in fx.accounts
            for i in a["interactions"]
        ],
        "account_fact": [
            fixture_id(slug, "account_fact", f["key"]) for a in fx.accounts for f in a["facts"]
        ],
    }
    return ids
