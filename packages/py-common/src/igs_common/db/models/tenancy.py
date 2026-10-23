import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import DateTime, ForeignKey, Index, String, Text
from sqlalchemy.dialects.postgresql import ARRAY, JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from igs_common.db.base import Base, IdMixin, TenantMixin, TimestampMixin
from igs_common.db.enums import UserRole, pg_enum


class Tenant(IdMixin, TimestampMixin, Base):
    """An operator hosted by IGS OS. Not tenant-scoped itself."""

    __tablename__ = "tenants"

    slug: Mapped[str] = mapped_column(String(63), unique=True)
    name: Mapped[str] = mapped_column(Text)
    settings: Mapped[dict[str, Any]] = mapped_column(JSONB, server_default="{}")


class User(IdMixin, TimestampMixin, TenantMixin, Base):
    __tablename__ = "users"
    __table_args__ = (Index("uq_users_tenant_email", "tenant_id", "email", unique=True),)

    email: Mapped[str] = mapped_column(Text)
    name: Mapped[str] = mapped_column(Text)
    role: Mapped[UserRole] = mapped_column(pg_enum(UserRole, "user_role"))
    auth_subject: Mapped[str | None] = mapped_column(Text)
    last_seen_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class ApiKey(IdMixin, TimestampMixin, TenantMixin, Base):
    """MCP clients and service-to-service callers. Plaintext is shown once; we store sha256."""

    __tablename__ = "api_keys"
    __table_args__ = (Index("ix_api_keys_tenant_prefix", "tenant_id", "prefix"),)

    name: Mapped[str] = mapped_column(Text)
    hash: Mapped[str] = mapped_column(String(64), unique=True)
    prefix: Mapped[str] = mapped_column(String(16))
    scopes: Mapped[list[str]] = mapped_column(ARRAY(Text), server_default="{}")
    created_by: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL")
    )
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
