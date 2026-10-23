"""Account 360 against a migrated + seeded Postgres (`docker compose up -d db`)."""

import asyncio
import os
from collections.abc import AsyncIterator, Iterator
from contextlib import asynccontextmanager
from datetime import date
from pathlib import Path
from uuid import UUID

import asyncpg
import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker
from sqlalchemy.pool import NullPool

from igs_common.accounts import (
    AccountIntelligence,
    AccountNotFoundError,
    ExtractionResult,
    InteractionInput,
    Passage,
    apply_extraction,
    load_snapshot,
)
from igs_common.accounts.ask import NO_INFO
from igs_common.accounts.extraction import AcceptedFact
from igs_common.db.enums import FactKind, StakeholderRole
from igs_common.db.models import AccountFact, Interaction, Stakeholder
from igs_common.db.session import create_engine, session_scope
from igs_common.llm import FakeLLM, Role, Scripted, Usage
from igs_common.seed import fixture_id, load

ADMIN_URL = os.environ.get("IGS_TEST_ADMIN_URL", "postgresql://igs:igs@localhost:5433/igs")
TEST_DB = "igs_test_w4"
ALEMBIC_INI = Path(__file__).resolve().parents[2] / "alembic.ini"
TODAY = date(2026, 10, 22)


def _id(kind: str, key: str) -> UUID:
    return fixture_id("igs", kind, key)


LAKESHORE = _id("account", "acc-lakeshore")
NORTHFIELD = _id("account", "acc-northfield")


def _test_url() -> str:
    return ADMIN_URL.rsplit("/", 1)[0] + f"/{TEST_DB}"


async def _recreate_database() -> None:
    conn = await asyncpg.connect(ADMIN_URL)
    try:
        await conn.execute(f'DROP DATABASE IF EXISTS "{TEST_DB}" WITH (FORCE)')
        await conn.execute(f'CREATE DATABASE "{TEST_DB}"')
    finally:
        await conn.close()


async def _seed(url: str) -> None:
    engine = create_engine(url, poolclass=NullPool)
    try:
        async with async_sessionmaker(engine)() as session, session.begin():
            await load(session)
    finally:
        await engine.dispose()


@pytest.fixture(scope="module")
def seeded_url() -> Iterator[str]:
    try:
        asyncio.run(_recreate_database())
    except (OSError, asyncpg.PostgresError) as exc:  # pragma: no cover - env dependent
        pytest.skip(f"local Postgres not available: {exc}")
    cfg = Config(str(ALEMBIC_INI))
    cfg.cmd_opts = type("Opts", (), {"x": [f"url={_test_url()}"]})()  # type: ignore[assignment]
    command.upgrade(cfg, "head")
    asyncio.run(_seed(_test_url()))
    yield _test_url()


@pytest.fixture
async def engine(seeded_url: str) -> AsyncIterator[AsyncEngine]:
    eng = create_engine(seeded_url, poolclass=NullPool)
    yield eng
    await eng.dispose()


def _tenant() -> UUID:
    return _id("tenant", "igs")


async def _tenant_id(engine: AsyncEngine) -> UUID:
    async with async_sessionmaker(engine)() as session:
        account = await session.get(Interaction, _id("interaction", "int-lak-03"))
        assert account is not None
        return account.tenant_id


def _factory(engine: AsyncEngine):  # noqa: ANN202
    @asynccontextmanager
    async def factory(tenant_id: UUID) -> AsyncIterator[AsyncSession]:
        async with session_scope(tenant_id, engine=engine) as session:
            yield session

    return factory


class FakeRetriever:
    def __init__(self, passages: list[Passage]) -> None:
        self.passages = passages
        self.calls: list[dict[str, object]] = []

    async def search(self, *, tenant_id: UUID, account_id: UUID, query: str, k: int):  # noqa: ANN201
        self.calls.append({"tenant_id": tenant_id, "account_id": account_id, "k": k})
        return self.passages


def _service(engine: AsyncEngine, llm: FakeLLM, retriever: FakeRetriever) -> AccountIntelligence:
    return AccountIntelligence(
        llm=llm,
        retriever=retriever,
        session_factory=_factory(engine),
        model_for=lambda role: f"model-{role.value}",
        today=lambda: TODAY,
    )


async def test_snapshot_reads_structured_state(engine: AsyncEngine) -> None:
    tenant = await _tenant_id(engine)
    async with session_scope(tenant, engine=engine) as session:
        snap = await load_snapshot(session, tenant_id=tenant, account_id=LAKESHORE, today=TODAY)
    assert snap is not None and snap.name == "Lakeshore University"
    assert len(snap.stakeholders) == 6
    assert any(
        p.name == "Robert Haines" and p.role is StakeholderRole.ATHLETIC_DIRECTOR
        for p in snap.stakeholders
    )
    assert [t.code for t in snap.trips] == ["IGS-2711"]
    assert snap.trips[0].balance_usd and snap.trips[0].balance_usd > 0
    # The team enrollment (24 × US$95, due a week before the anchor) comes from the schedule.
    payments = snap.trips[0].payments
    assert payments is not None and payments.overdue_usd == 2280
    assert payments.oldest_overdue_days == 7
    assert len(snap.interactions) == 12  # bounded window
    # every fact's source is citable, even when older than the window
    assert all(snap.interaction(f.source_interaction_id) for f in snap.facts)

    async with session_scope(tenant, engine=engine) as session:
        other = await load_snapshot(session, tenant_id=UUID(int=9), account_id=LAKESHORE)
    assert other is None


async def test_brief_is_cached_until_inputs_change(engine: AsyncEngine) -> None:
    tenant = await _tenant_id(engine)
    script = {"sentences": [{"text": "Lakeshore viaja en marzo.", "sources": [0]}]}
    llm = FakeLLM([Scripted(json=script), Scripted(json=script)])
    service = _service(engine, llm, FakeRetriever([]))

    first, cached = await service.brief(tenant_id=tenant, account_id=LAKESHORE)
    assert not cached and first.text == "Lakeshore viaja en marzo. [1]"
    assert first.health.value == "red"
    assert any("enrollment fees" in r for r in first.health_reasons)
    again, cached = await service.brief(tenant_id=tenant, account_id=LAKESHORE)
    assert cached and again.inputs_hash == first.inputs_hash and again.text == first.text
    assert len(llm.requests) == 1

    _, cached = await service.brief(tenant_id=tenant, account_id=LAKESHORE, refresh=True)
    assert not cached and len(llm.requests) == 2
    assert llm.requests[0].role is Role.AGENT

    with pytest.raises(AccountNotFoundError):
        await service.brief(tenant_id=tenant, account_id=UUID(int=404))


async def test_ask_uses_only_this_accounts_passages(engine: AsyncEngine) -> None:
    tenant = await _tenant_id(engine)
    async with async_sessionmaker(engine)() as session:
        mine = await session.get(Interaction, _id("interaction", "int-lak-03"))
        foreign = (
            await session.execute(
                select(Interaction).where(Interaction.account_id == NORTHFIELD).limit(1)
            )
        ).scalar_one()
    assert mine is not None
    retriever = FakeRetriever(
        [
            Passage(mine.id, mine.body[:300], 0.9),
            Passage(foreign.id, "NORTHFIELD SECRET " + foreign.body[:100], 0.8),
        ]
    )
    llm = FakeLLM(
        [
            Scripted(
                json={
                    "answerable": True,
                    "sentences": [
                        {"text": "Robert Haines firma los contratos.", "sources": [0]},
                    ],
                }
            )
        ]
    )
    answer = await _service(engine, llm, retriever).ask(
        tenant_id=tenant, account_id=LAKESHORE, question="¿Quién decide en Lakeshore?"
    )
    assert answer.grounded and answer.citations[0].interaction_id is None
    assert answer.passages_used == 1
    prompt = llm.requests[0].items[0].content  # type: ignore[union-attr]
    assert mine.body[:60] in prompt
    assert "NORTHFIELD SECRET" not in prompt
    assert retriever.calls == [{"tenant_id": tenant, "account_id": LAKESHORE, "k": 6}]


async def test_ask_abstains_when_not_grounded(engine: AsyncEngine) -> None:
    tenant = await _tenant_id(engine)
    llm = FakeLLM([Scripted(json={"answerable": False, "sentences": []})])
    answer = await _service(engine, llm, FakeRetriever([])).ask(
        tenant_id=tenant, account_id=LAKESHORE, question="What is the coach's favourite color?"
    )
    assert not answer.grounded and answer.citations == ()
    assert answer.text.startswith(NO_INFO["en"]) and "Robert Haines" in answer.text


async def test_apply_extraction_writes_provenance_and_supersedes(engine: AsyncEngine) -> None:
    tenant = await _tenant_id(engine)
    source = _id("interaction", "int-lak-12")
    async with session_scope(tenant, engine=engine) as session:
        interaction = await session.get(Interaction, source)
        assert interaction is not None
        old = (
            (
                await session.execute(
                    select(AccountFact).where(
                        AccountFact.account_id == LAKESHORE, AccountFact.superseded_by.is_(None)
                    )
                )
            )
            .scalars()
            .first()
        )
        assert old is not None
        new_ids = await apply_extraction(
            session,
            tenant_id=tenant,
            interaction=InteractionInput(
                id=interaction.id,
                account_id=LAKESHORE,
                occurred_at=interaction.occurred_at,
                channel=interaction.channel.value,
                body=interaction.body,
                stakeholder_id=interaction.stakeholder_id,
            ),
            result=ExtractionResult(
                interaction_id=interaction.id,
                facts=(
                    AcceptedFact(
                        kind=FactKind.STATUS,
                        statement="Balance payment scheduled after PO approval.",
                        evidence=interaction.body[:40],
                        confidence=0.9,
                        severity=None,
                        due_date=None,
                        supersedes=(old.id,),
                    ),
                ),
                suggestions=(),
                rejected=(),
                model="fake",
                usage=Usage(),
            ),
        )
        old_id, stakeholder_id = old.id, interaction.stakeholder_id

    async with session_scope(tenant, engine=engine) as session:
        refreshed = await session.get(AccountFact, old_id)
        new = await session.get(AccountFact, new_ids[0])
        assert refreshed is not None and new is not None
        assert refreshed.superseded_by == new.id
        assert new.source_interaction_id == source and new.superseded_by is None
        if stakeholder_id is not None:
            person = await session.get(Stakeholder, stakeholder_id)
            assert person is not None and person.last_contact_at is not None
