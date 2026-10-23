from collections.abc import AsyncIterator
from datetime import UTC, date, datetime
from uuid import UUID, uuid4

import httpx
import pytest
from core_test_support import API_KEY, DEMO_TENANT, OTHER_TENANT

from igs_core.app import create_app
from igs_core.config import Settings
from igs_core.deps import hash_api_key
from igs_core.repositories import Principal, Repositories
from igs_core.schemas.accounts import AccountDetail, AccountSummary, Stakeholder
from igs_core.schemas.trips import TripDetail, TripItem, TripSummary, TripTeam


def _trip(n: int, tenant: UUID) -> TripDetail:
    return TripDetail(
        id=UUID(int=n),
        title=f"Trip {n}",
        city="Buenos Aires",
        country="Argentina",
        start_date=date(2027, 3, n),
        end_date=date(2027, 3, n + 9),
        status="proposed",
        price_per_person_usd=2890,
        team=TripTeam(lead_id=UUID(int=100 + n), organization="Lakeshore University"),
        summary="Women's soccer tour",
        items=[
            TripItem(
                id=uuid4(),
                day=1,
                slot="morning",
                kind="arrival",
                title="Arrival",
                status="confirmed",
            )
        ],
    )


class FakeDirectory:
    def __init__(self) -> None:
        self.ready = True

    async def tenant_id_by_slug(self, slug: str) -> UUID | None:
        return DEMO_TENANT if slug == Settings().demo_tenant_slug else None

    async def principal_for_api_key(self, key_hash: str) -> Principal | None:
        if key_hash != hash_api_key(API_KEY):
            return None
        return Principal(
            kind="api_key",
            tenant_id=OTHER_TENANT,
            role="ops",
            subject="api_key:1",
            scopes=frozenset({"trips:read"}),
        )

    async def ping(self) -> None:
        if not self.ready:
            raise ConnectionError("db down")


class FakeTrips:
    def __init__(self) -> None:
        self.rows = {t: [_trip(n, t) for n in range(1, 6)] for t in (DEMO_TENANT, OTHER_TENANT)}

    async def list(self, tenant_id, *, status, from_date, after, limit) -> list[TripSummary]:
        rows = [r for r in self.rows[tenant_id] if status is None or r.status == status]
        if from_date:
            rows = [r for r in rows if r.start_date >= from_date]
        if after:
            rows = [r for r in rows if (r.start_date, r.id) > after]
        return [TripSummary(**r.model_dump(exclude={"summary", "pricing", "items"})) for r in rows][
            :limit
        ]

    async def get(self, tenant_id, trip_id) -> TripDetail | None:
        return next((r for r in self.rows[tenant_id] if r.id == trip_id), None)


class FakeAccounts:
    def __init__(self) -> None:
        self.account = AccountDetail(
            id=UUID(int=7),
            name="Lakeshore University",
            kind="university",
            country="USA",
            status="active",
            health="amber",
            created_at=datetime(2026, 1, 1, tzinfo=UTC),
            stakeholders=[
                Stakeholder(
                    id=uuid4(),
                    name="Dana Whitfield",
                    role="coach",
                    influence=5,
                    sentiment="positive",
                )
            ],
            facts=[],
            recent_interactions=[],
        )

    async def list(self, tenant_id, *, status, health, after, limit) -> list[AccountSummary]:
        if tenant_id != DEMO_TENANT:
            return []
        return [AccountSummary(**self.account.model_dump())][:limit]

    async def get(self, tenant_id, account_id) -> AccountDetail | None:
        if tenant_id == DEMO_TENANT and account_id == self.account.id:
            return self.account
        return None


@pytest.fixture
def repos() -> Repositories:
    return Repositories(directory=FakeDirectory(), trips=FakeTrips(), accounts=FakeAccounts())


@pytest.fixture
def settings() -> Settings:
    return Settings(environment="test", demo_mode=True, page_size_default=2)


@pytest.fixture
async def client(settings: Settings, repos: Repositories) -> AsyncIterator[httpx.AsyncClient]:
    app = create_app(settings, repos=repos)
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as c:
        yield c


# Databases the integration modules connect to (see their module docstrings). Created and
# migrated once per session so the suite runs in CI and on a fresh machine without setup.
_INTEGRATION_DBS = (
    "igs_test_p4",
    "igs_test_w9",
    "igs_test_x7",
    "igs_test_mint",
    "igs_test_y4",
    "igs_test_c4api",
    "igs_test_r6",
    "igs_test_c9",
)


@pytest.fixture(scope="session", autouse=True)
def _integration_databases() -> None:
    from igs_common.testing import DatabaseUnavailableError, prepare_database

    for name in _INTEGRATION_DBS:
        try:
            prepare_database(name)
        except DatabaseUnavailableError:
            return  # the integration modules skip themselves when Postgres is down
