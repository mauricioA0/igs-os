"""SQL read models over the tables defined in docs/architecture/data-model.md.

Queries are written against table/column names (the documented contract) rather than ORM
classes, so the read side stays stable while models evolve. Every query also filters by
``tenant_id`` explicitly, on top of row-level security.
"""

from collections.abc import Callable
from contextlib import AbstractAsyncContextManager
from datetime import date
from typing import Any
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession

from igs_core.repositories.base import Principal
from igs_core.schemas.accounts import (
    AccountDetail,
    AccountFact,
    AccountSummary,
    InteractionSummary,
    Stakeholder,
)
from igs_core.schemas.trips import (
    ItemOpponent,
    ItemProvider,
    TripDetail,
    TripItem,
    TripSummary,
    TripTeam,
)

SessionFactory = Callable[[UUID], AbstractAsyncContextManager[AsyncSession]]


class SqlDirectory:
    def __init__(self, engine: AsyncEngine) -> None:
        self.engine = engine

    async def tenant_id_by_slug(self, slug: str) -> UUID | None:
        async with self.engine.connect() as conn:
            row = await conn.execute(
                text("select id from tenants where slug = :slug"), {"slug": slug}
            )
            return row.scalar_one_or_none()

    async def principal_for_api_key(self, key_hash: str) -> Principal | None:
        # Runs before the tenant is known, so it can't read api_keys under RLS. The SECURITY
        # DEFINER function `resolve_api_key` (migration 0002) does the cross-tenant lookup and
        # only ever returns active keys.
        sql = text("select api_key_id, tenant_id, scopes, role from resolve_api_key(:hash)")
        async with self.engine.connect() as conn:
            row = (await conn.execute(sql, {"hash": key_hash})).mappings().first()
        if row is None:
            return None
        return Principal(
            kind="api_key",
            tenant_id=row["tenant_id"],
            role=row["role"],
            subject=f"api_key:{row['api_key_id']}",
            scopes=frozenset(row["scopes"] or ()),
        )

    async def ping(self) -> None:
        async with self.engine.connect() as conn:
            await conn.execute(text("select 1"))


_TRIP_COLUMNS = """
    t.id, t.code, t.account_id, t.title, t.city, t.country, t.start_date, t.end_date,
    t.status::text as status,
    t.price_per_person_usd, t.lead_id,
    c.organization, c.name as coach_name,
    l.sport::text as sport, l.gender::text as gender, l.age_group, l.level_score, l.group_size
"""

_TRIP_FROM = """
    from trips t
    join leads l on l.id = t.lead_id and l.tenant_id = t.tenant_id
    left join contacts c on c.id = l.contact_id and c.tenant_id = t.tenant_id
"""


def _trip_summary(row: Any) -> dict[str, Any]:
    return {
        "id": row["id"],
        "code": row["code"],
        "account_id": row["account_id"],
        "title": row["title"],
        "city": row["city"],
        "country": row["country"],
        "start_date": row["start_date"],
        "end_date": row["end_date"],
        "status": row["status"],
        "price_per_person_usd": row["price_per_person_usd"],
        "team": TripTeam(
            lead_id=row["lead_id"],
            organization=row["organization"],
            coach_name=row["coach_name"],
            sport=row["sport"],
            gender=row["gender"],
            age_group=row["age_group"],
            level_score=row["level_score"],
            group_size=row["group_size"],
        ),
    }


class SqlTrips:
    def __init__(self, sessions: SessionFactory) -> None:
        self.sessions = sessions

    async def list(
        self,
        tenant_id: UUID,
        *,
        status: str | None,
        from_date: date | None,
        after: tuple[date, UUID] | None,
        limit: int,
    ) -> list[TripSummary]:
        sql = text(
            f"""
            select {_TRIP_COLUMNS} {_TRIP_FROM}
            where t.tenant_id = :tenant_id
              and (cast(:status as text) is null or t.status::text = :status)
              and (cast(:from_date as date) is null or t.start_date >= :from_date)
              and (cast(:after_date as date) is null
                   or (t.start_date, t.id) > (cast(:after_date as date), cast(:after_id as uuid)))
            order by t.start_date, t.id
            limit :limit
            """  # noqa: S608 — static fragments only, all values are bound
        )
        params = {
            "tenant_id": tenant_id,
            "status": status,
            "from_date": from_date,
            "after_date": after[0] if after else None,
            "after_id": after[1] if after else None,
            "limit": limit,
        }
        async with self.sessions(tenant_id) as session:
            rows = (await session.execute(sql, params)).mappings().all()
        return [TripSummary(**_trip_summary(r)) for r in rows]

    async def get(self, tenant_id: UUID, trip_id: UUID) -> TripDetail | None:
        trip_sql = text(
            f"""
            select {_TRIP_COLUMNS}, t.summary, t.pricing {_TRIP_FROM}
            where t.tenant_id = :tenant_id and t.id = :trip_id
            """  # noqa: S608
        )
        items_sql = text(
            """
            select i.id, i.day, i.slot::text as slot, i.kind::text as kind, i.title,
                   i.status::text as status, i.opponent_id, i.experience_id, i.provider_id,
                   i.notes, i.time, i.alert, i.requested_at, i.confirmed_at, i.completed_at,
                   i.result, o.name as opponent_name, o.level_score as opponent_level,
                   p.name as provider_name, p.kind::text as provider_kind
            from trip_items i
            left join opponents o on o.id = i.opponent_id and o.tenant_id = i.tenant_id
            left join providers p on p.id = i.provider_id and p.tenant_id = i.tenant_id
            where i.tenant_id = :tenant_id and i.trip_id = :trip_id
            order by i.day,
                     case i.slot::text when 'morning' then 0 when 'afternoon' then 1 else 2 end,
                     i.id
            """
        )
        params = {"tenant_id": tenant_id, "trip_id": trip_id}
        async with self.sessions(tenant_id) as session:
            row = (await session.execute(trip_sql, params)).mappings().first()
            if row is None:
                return None
            items = (await session.execute(items_sql, params)).mappings().all()
        return TripDetail(
            **_trip_summary(row),
            summary=row["summary"],
            pricing=row["pricing"],
            items=[trip_item(i) for i in items],
        )


def trip_item(row: Any) -> TripItem:
    """Item row (with joined opponent/provider columns) → API schema."""
    r = dict(row)
    opponent_name, opponent_level = r.pop("opponent_name", None), r.pop("opponent_level", None)
    provider_name, provider_kind = r.pop("provider_name", None), r.pop("provider_kind", None)
    return TripItem(
        **r,
        opponent=ItemOpponent(name=opponent_name, level_score=opponent_level)
        if opponent_name is not None and opponent_level is not None
        else None,
        provider=ItemProvider(name=provider_name, kind=provider_kind)
        if provider_name is not None and provider_kind is not None
        else None,
    )


_ACCOUNT_COLUMNS = """
    id, name, kind::text as kind, country, state, city,
    coalesce(sport_programs, '{}') as sport_programs, tier, status::text as status,
    health::text as health, created_at
"""


class SqlAccounts:
    def __init__(self, sessions: SessionFactory) -> None:
        self.sessions = sessions

    async def list(
        self,
        tenant_id: UUID,
        *,
        status: str | None,
        health: str | None,
        after: tuple[str, UUID] | None,
        limit: int,
    ) -> list[AccountSummary]:
        sql = text(
            f"""
            select {_ACCOUNT_COLUMNS}
            from accounts
            where tenant_id = :tenant_id
              and (cast(:status as text) is null or status::text = :status)
              and (cast(:health as text) is null or health::text = :health)
              and (cast(:after_name as text) is null
                   or (name, id) > (cast(:after_name as text), cast(:after_id as uuid)))
            order by name, id
            limit :limit
            """  # noqa: S608
        )
        params = {
            "tenant_id": tenant_id,
            "status": status,
            "health": health,
            "after_name": after[0] if after else None,
            "after_id": after[1] if after else None,
            "limit": limit,
        }
        async with self.sessions(tenant_id) as session:
            rows = (await session.execute(sql, params)).mappings().all()
        return [AccountSummary(**dict(r)) for r in rows]

    async def get(self, tenant_id: UUID, account_id: UUID) -> AccountDetail | None:
        params = {"tenant_id": tenant_id, "account_id": account_id}
        account_sql = text(
            f"select {_ACCOUNT_COLUMNS} from accounts "  # noqa: S608
            "where tenant_id = :tenant_id and id = :account_id"
        )
        stakeholders_sql = text(
            """
            select id, name, title, role::text as role, influence, sentiment::text as sentiment,
                   email, phone, preferred_channel::text as preferred_channel,
                   last_contact_at, notes
            from stakeholders
            where tenant_id = :tenant_id and account_id = :account_id
            order by influence desc, name
            """
        )
        facts_sql = text(
            """
            select id, kind::text as kind, statement, confidence, source_interaction_id, valid_from
            from account_facts
            where tenant_id = :tenant_id and account_id = :account_id and superseded_by is null
            order by valid_from desc nulls last, id
            """
        )
        interactions_sql = text(
            """
            select id, channel::text as channel, direction::text as direction, occurred_at,
                   subject, stakeholder_id, trip_id, lead_id,
                   case
                       when exists (
                           select 1 from document_chunks c
                           where c.interaction_id = interactions.id and c.quarantined
                       )
                       -- Quarantined at ingestion (instructions aimed at AI agents): the copilot
                       -- reads this summary too, so the text stays out until a person clears it.
                       then '[flagged as possible prompt injection: review before acting]'
                       else nullif(
                           left(regexp_replace(coalesce(body, ''), '[[:space:]]+', ' ', 'g'), 280),
                           ''
                       )
                   end as excerpt
            from interactions
            where tenant_id = :tenant_id and account_id = :account_id
            order by occurred_at desc
            limit 20
            """
        )
        async with self.sessions(tenant_id) as session:
            row = (await session.execute(account_sql, params)).mappings().first()
            if row is None:
                return None
            stakeholders = (await session.execute(stakeholders_sql, params)).mappings().all()
            facts = (await session.execute(facts_sql, params)).mappings().all()
            interactions = (await session.execute(interactions_sql, params)).mappings().all()
        return AccountDetail(
            **dict(row),
            stakeholders=[Stakeholder(**dict(s)) for s in stakeholders],
            facts=[AccountFact(**dict(f)) for f in facts],
            recent_interactions=[InteractionSummary(**dict(i)) for i in interactions],
        )
