import uuid

from sqlalchemy import CheckConstraint, Float, ForeignKey, Index, Integer, Text
from sqlalchemy.dialects.postgresql import ARRAY, UUID
from sqlalchemy.orm import Mapped, mapped_column

from igs_common.db.base import Base, IdMixin, TenantMixin, TimestampMixin
from igs_common.db.enums import Gender, ProviderKind, Sport, pg_enum


class Provider(IdMixin, TimestampMixin, TenantMixin, Base):
    __tablename__ = "providers"
    __table_args__ = (Index("ix_providers_tenant_kind_city", "tenant_id", "kind", "city"),)

    name: Mapped[str] = mapped_column(Text)
    kind: Mapped[ProviderKind] = mapped_column(pg_enum(ProviderKind, "provider_kind"))
    city: Mapped[str] = mapped_column(Text)
    country: Mapped[str] = mapped_column(Text)
    contact: Mapped[str] = mapped_column(Text)
    unit_price_usd: Mapped[int] = mapped_column(Integer)
    unit: Mapped[str] = mapped_column(Text)


class Opponent(IdMixin, TimestampMixin, TenantMixin, Base):
    """Embeddings live in the vector store (`catalog_items`), not here."""

    __tablename__ = "opponents"
    __table_args__ = (
        CheckConstraint("level_score BETWEEN 1 AND 10", name="level_score_range"),
        Index("ix_opponents_tenant_filters", "tenant_id", "sport", "gender", "country"),
        Index("ix_opponents_age_groups", "age_groups", postgresql_using="gin"),
    )

    name: Mapped[str] = mapped_column(Text)
    city: Mapped[str] = mapped_column(Text)
    country: Mapped[str] = mapped_column(Text)
    sport: Mapped[Sport] = mapped_column(pg_enum(Sport, "sport"))
    gender: Mapped[Gender] = mapped_column(pg_enum(Gender, "gender"))
    age_groups: Mapped[list[str]] = mapped_column(ARRAY(Text))
    level_score: Mapped[int] = mapped_column(Integer)
    description: Mapped[str] = mapped_column(Text)
    provider_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("providers.id", ondelete="SET NULL")
    )


class Experience(IdMixin, TimestampMixin, TenantMixin, Base):
    __tablename__ = "experiences"
    __table_args__ = (
        Index("ix_experiences_tenant_country", "tenant_id", "country"),
        Index("ix_experiences_sports", "sports", postgresql_using="gin"),
    )

    title: Mapped[str] = mapped_column(Text)
    city: Mapped[str] = mapped_column(Text)
    country: Mapped[str] = mapped_column(Text)
    sports: Mapped[list[str]] = mapped_column(ARRAY(Text), server_default="{}")  # empty = any
    duration_hours: Mapped[float] = mapped_column(Float)
    price_usd: Mapped[int] = mapped_column(Integer)
    description: Mapped[str] = mapped_column(Text)
    provider_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("providers.id", ondelete="SET NULL")
    )
