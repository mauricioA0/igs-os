"""The travelers roster: tenant isolation and the minors' data guard."""

import uuid

import pytest
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncEngine

from igs_common.db import session_scope
from igs_common.db.enums import TravelerRole
from igs_common.db.models import Traveler, Trip
from igs_common.db.rls import APP_ROLE

from .test_db_rls import _make_tenant


async def _trip_id(engine: AsyncEngine, tenant: uuid.UUID) -> uuid.UUID:
    async with session_scope(tenant, engine=engine, role=APP_ROLE) as s:
        return (await s.scalars(select(Trip.id))).one()


async def test_roster_is_tenant_scoped(engine: AsyncEngine) -> None:
    alpha, beta = await _make_tenant(engine, "ra"), await _make_tenant(engine, "rb")
    trip = await _trip_id(engine, alpha)
    async with session_scope(alpha, engine=engine, role=APP_ROLE) as s:
        s.add(Traveler(tenant_id=alpha, trip_id=trip, full_name="Ana", role=TravelerRole.PLAYER))
    async with session_scope(beta, engine=engine, role=APP_ROLE) as s:
        assert (await s.scalars(select(Traveler))).all() == []
    async with session_scope(alpha, engine=engine, role=APP_ROLE) as s:
        assert [t.full_name for t in (await s.scalars(select(Traveler))).all()] == ["Ana"]


async def test_minors_cannot_have_their_own_contact(engine: AsyncEngine) -> None:
    tenant = await _make_tenant(engine, "rm")
    trip = await _trip_id(engine, tenant)
    with pytest.raises(IntegrityError, match="minor_no_contact"):
        async with session_scope(tenant, engine=engine, role=APP_ROLE) as s:
            s.add(
                Traveler(
                    tenant_id=tenant,
                    trip_id=trip,
                    full_name="Kid",
                    role=TravelerRole.PLAYER,
                    is_minor=True,
                    email="kid@example.com",
                )
            )
