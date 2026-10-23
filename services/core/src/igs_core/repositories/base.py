"""Read ports the routers depend on. SQL implementations live in ``sql.py``; tests use fakes."""

from dataclasses import dataclass, field
from datetime import date
from typing import Literal, Protocol
from uuid import UUID

from igs_core.schemas.accounts import AccountDetail, AccountSummary
from igs_core.schemas.trips import TripDetail, TripSummary

Role = Literal["owner", "ops", "sales", "viewer"]


@dataclass(frozen=True)
class Principal:
    kind: Literal["demo", "api_key", "user"]
    tenant_id: UUID
    role: Role
    subject: str
    scopes: frozenset[str] = field(default_factory=frozenset)


class Directory(Protocol):
    """Resolves who is calling. Runs before the tenant is known."""

    async def tenant_id_by_slug(self, slug: str) -> UUID | None: ...

    async def principal_for_api_key(self, key_hash: str) -> Principal | None: ...

    async def ping(self) -> None: ...


class TripsRepo(Protocol):
    async def list(
        self,
        tenant_id: UUID,
        *,
        status: str | None,
        from_date: date | None,
        after: tuple[date, UUID] | None,
        limit: int,
    ) -> list[TripSummary]: ...

    async def get(self, tenant_id: UUID, trip_id: UUID) -> TripDetail | None: ...


class AccountsRepo(Protocol):
    async def list(
        self,
        tenant_id: UUID,
        *,
        status: str | None,
        health: str | None,
        after: tuple[str, UUID] | None,
        limit: int,
    ) -> list[AccountSummary]: ...

    async def get(self, tenant_id: UUID, account_id: UUID) -> AccountDetail | None: ...


@dataclass
class Repositories:
    directory: Directory
    trips: TripsRepo
    accounts: AccountsRepo
