"""End to end against Postgres: dry run, apply, re-run idempotency, all-or-nothing, RLS.

Database ``igs_test_c4`` is created, migrated and seeded with the demo tenant here.
"""

import io
from collections.abc import AsyncIterator, Callable
from contextlib import AbstractAsyncContextManager
from uuid import UUID

import pytest
from openpyxl import Workbook
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession
from sqlalchemy.pool import NullPool

from igs_common.db import session_scope, system_scope, uuid7
from igs_common.db.models import Account, AuditLog, Provider, Stakeholder, Tenant, Traveler, Trip
from igs_common.db.rls import APP_ROLE
from igs_common.db.session import create_engine
from igs_common.importer import import_file
from igs_common.seed import fixture_id, load
from igs_common.testing import DatabaseUnavailableError, prepare_database

pytestmark = pytest.mark.asyncio(loop_scope="session")

LAKESHORE = fixture_id("igs", "account", "acc-lakeshore")


@pytest.fixture(scope="module")
def db_url() -> str:
    try:
        return prepare_database("igs_test_c4")
    except DatabaseUnavailableError as exc:
        pytest.skip(f"Postgres not reachable: {exc}")


@pytest.fixture(scope="module")
async def env(db_url: str) -> AsyncIterator[tuple[AsyncEngine, UUID]]:
    engine = create_engine(db_url, poolclass=NullPool)
    async with system_scope(engine=engine) as s:
        await load(s)
    async with system_scope(engine=engine) as s:
        tenant = await s.scalar(select(Tenant.id).where(Tenant.slug == "igs"))
    assert tenant is not None
    yield engine, tenant
    await engine.dispose()


def _sessions(engine: AsyncEngine) -> Callable[[UUID], AbstractAsyncContextManager[AsyncSession]]:
    return lambda t: session_scope(t, engine=engine, role=APP_ROLE)


def _book(**sheets: list[list[object]]) -> bytes:
    wb = Workbook()
    for ws in list(wb.worksheets):
        wb.remove(ws)
    for name, rows in sheets.items():
        ws = wb.create_sheet(name)
        for r in rows:
            ws.append(r)
    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


BOOK = _book(
    Clientes=[
        ["Nombre", "Tipo", "País", "Ciudad", "Deportes"],
        ["Lakeshore University", "university", "USA", "Evanston", None],
        ["Harbor Point Academy", "Colegio", "USA", "Boston", "girls' soccer, field hockey"],
    ],
    Contactos=[
        ["Cliente", "Nombre", "Cargo", "Rol", "Correo", "Influencia"],
        ["Harbor Point Academy", "Morgan Lee", "Athletic Director", "AD", "mlee@hpa.example", 5],
        ["lakeshore university", "Dana Whitfield", "Head Coach", "coach", None, None],
    ],
    Proveedores=[
        ["Proveedor", "Rubro", "Ciudad", "País", "Contacto", "Tarifa", "Unidad"],
        ["Micros del Sur", "micro", "Rosario", "Argentina", "+54 341 555 0101", "US$ 650", "day"],
    ],
    Viajes=[
        ["Código", "Cliente", "Título", "Ciudad", "País", "Inicio", "Fin", "Precio", "Pax"],
        [
            "IGS-3001",
            "Harbor Point Academy",
            "Girls' Soccer — Rosario",
            "Rosario",
            "Argentina",
            "2027-06-20",
            "2027-06-28",
            "2.650",
            18,
        ],
    ],
    Plantel=[
        ["Viaje", "Nombre", "Rol", "Menor", "Año nacimiento", "Correo", "Pasaporte"],
        ["IGS-3001", "Riley Chen", "jugadora", "si", 2010, "riley@kid.example", "X123"],
        ["IGS-3001", "Sam Ortiz", "jugadora", "si", 2011, None, "X456"],
        ["IGS-3001", "Morgan Lee", "staff", "no", None, "mlee@hpa.example", None],
    ],
    Pagos=[
        ["Viaje", "Recibo", "Concepto", "Monto", "Vencimiento", "Pagado"],
        ["IGS-3001", "INV-1", "inscripción", "US$ 1,710", "2026-11-01", "2026-10-20"],
        ["IGS-3001", "INV-2", "cuota", 500, "2026-12-01", None],
    ],
    Notas=[["anything", "else"], ["is", "ignored"]],
)


async def _count(engine: AsyncEngine, tenant: UUID, model: type) -> int:
    async with session_scope(tenant, engine=engine, role=APP_ROLE) as s:
        return int(await s.scalar(select(func.count()).select_from(model)) or 0)


async def test_dry_run_reports_everything_and_writes_nothing(env) -> None:
    engine, tenant = env
    before = {m: await _count(engine, tenant, m) for m in (Account, Stakeholder, Trip, Traveler)}
    report = await import_file(BOOK, "igs.xlsx", tenant_id=tenant, sessions=_sessions(engine))
    assert report.dry_run and not report.applied
    assert report.errors == []
    s = {k: v.model_dump() for k, v in report.summary.items()}
    assert s["accounts"] == {"create": 1, "update": 1, "unchanged": 0}
    assert s["stakeholders"] == {"create": 1, "update": 1, "unchanged": 0}
    assert s["providers"]["create"] == 1
    assert s["trips"]["create"] == 1
    assert s["travelers"]["create"] == 3
    assert s["payments"]["create"] == 2
    lak = next(c for c in report.changes if c.entity == "accounts" and c.action == "update")
    assert lak.changes == {"city": ["Port Huron", "Evanston"]}
    codes = {i.code for i in report.issues}
    assert {"unknown-sheet", "column-not-stored", "minor-contact-dropped"} <= codes
    after = {m: await _count(engine, tenant, m) for m in before}
    assert after == before


async def test_apply_then_rerun_is_idempotent(env) -> None:
    engine, tenant = env
    seeded_travelers = await _count(engine, tenant, Traveler)
    report = await import_file(
        BOOK, "igs.xlsx", tenant_id=tenant, sessions=_sessions(engine), dry_run=False
    )
    assert report.applied, report.render_text()
    async with session_scope(tenant, engine=engine, role=APP_ROLE) as s:
        hpa = await s.scalar(select(Account).where(Account.name == "Harbor Point Academy"))
        assert hpa is not None and hpa.kind.value == "high_school"
        assert hpa.sport_programs == ["girls' soccer", "field hockey"]
        lak = await s.get(Account, LAKESHORE)
        assert lak is not None and lak.city == "Evanston"
        dana = await s.scalar(select(Stakeholder).where(Stakeholder.name == "Dana Whitfield"))
        assert dana is not None
        assert dana.title == "Head Coach"
        assert dana.email == "dwhitfield@lakeshore.example"  # empty cell never blanks
        assert dana.influence == 4
        trip = await s.scalar(select(Trip).where(Trip.code == "IGS-3001"))
        assert trip is not None and trip.account_id == hpa.id
        assert trip.price_per_person_usd == 2650
        assert trip.pricing["total_usd"] == 2650 * 18
        assert trip.pricing["paid_usd"] == 1710
        assert set(trip.pricing["payments"]) == {"INV-1", "INV-2"}
        roster = (await s.scalars(select(Traveler).where(Traveler.trip_id == trip.id))).all()
        riley = next(t for t in roster if t.full_name == "Riley Chen")
        assert riley.is_minor and riley.email is None and riley.birth_year == 2010
        bus = await s.scalar(select(Provider).where(Provider.name == "Micros del Sur"))
        assert bus is not None and bus.kind.value == "transport" and bus.unit_price_usd == 650
        audit = await s.scalar(select(AuditLog).where(AuditLog.action == "import.apply"))
        assert audit is not None and audit.after is not None
        assert audit.after["filename"] == "igs.xlsx"

    again = await import_file(
        BOOK, "igs.xlsx", tenant_id=tenant, sessions=_sessions(engine), dry_run=False
    )
    assert again.applied
    assert all(c.action == "unchanged" for c in again.changes), again.render_text()
    assert await _count(engine, tenant, Traveler) == seeded_travelers + 3


async def test_any_error_means_nothing_is_written(env) -> None:
    engine, tenant = env
    book = _book(
        accounts=[["name", "kind", "country"], ["Never Written FC", "club", "USA"]],
        payments=[
            ["trip_code", "payment_ref", "kind", "amount_usd", "due_date"],
            ["IGS-9999", "INV-9", "balance", 100, "2027-01-01"],
        ],
    )
    report = await import_file(
        book, "bad.xlsx", tenant_id=tenant, sessions=_sessions(engine), dry_run=False
    )
    assert not report.applied
    assert [i.code for i in report.errors] == ["unknown-reference"]
    async with session_scope(tenant, engine=engine, role=APP_ROLE) as s:
        assert await s.scalar(select(Account).where(Account.name == "Never Written FC")) is None


async def test_other_tenants_data_is_invisible(env) -> None:
    engine, _ = env
    other = uuid7()
    async with system_scope(engine=engine) as s:
        s.add(Tenant(id=other, slug=f"other-{other.hex[-8:]}", name="Other operator"))
    book = _book(
        payments=[
            ["trip_code", "payment_ref", "kind", "amount_usd", "due_date"],
            ["IGS-2711", "INV-X", "balance", 100, "2027-01-01"],
        ]
    )
    report = await import_file(book, "x.xlsx", tenant_id=other, sessions=_sessions(engine))
    assert [i.code for i in report.errors] == ["unknown-reference"]
