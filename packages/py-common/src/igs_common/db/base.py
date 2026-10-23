"""Declarative base, naming convention and shared column mixins."""

import os
import time
import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, MetaData, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import DeclarativeBase, Mapped, declared_attr, mapped_column

# Deterministic constraint names so Alembic autogenerate and downgrades stay stable.
NAMING_CONVENTION = {
    "ix": "ix_%(table_name)s_%(column_0_N_name)s",
    "uq": "uq_%(table_name)s_%(column_0_N_name)s",
    "ck": "ck_%(table_name)s_%(constraint_name)s",
    "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
    "pk": "pk_%(table_name)s",
}


def uuid7() -> uuid.UUID:
    """RFC 9562 UUIDv7: 48-bit unix ms timestamp + random. Time-ordered for index locality."""
    ms = time.time_ns() // 1_000_000
    rand = int.from_bytes(os.urandom(10), "big")
    rand_a = rand >> 68  # 12 bits
    rand_b = rand & ((1 << 62) - 1)  # 62 bits
    value = (ms << 80) | (0x7 << 76) | (rand_a << 64) | (0b10 << 62) | rand_b
    return uuid.UUID(int=value)


class Base(DeclarativeBase):
    metadata = MetaData(naming_convention=NAMING_CONVENTION)


class IdMixin:
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid7)


class TimestampMixin:
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )


class TenantMixin:
    """Every business table carries tenant_id; RLS policies key on it (see db/rls.py).

    No standalone index: each table declares composite indexes that lead with tenant_id.
    """

    __tenant_scoped__ = True

    @declared_attr
    def tenant_id(cls) -> Mapped[uuid.UUID]:  # noqa: N805
        return mapped_column(
            UUID(as_uuid=True),
            ForeignKey("tenants.id", ondelete="CASCADE"),
            nullable=False,
        )
