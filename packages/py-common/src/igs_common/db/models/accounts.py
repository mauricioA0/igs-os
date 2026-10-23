"""Account 360: the client (university, club…), its people, touchpoints and extracted facts."""

import uuid
from datetime import date, datetime
from typing import Any

from sqlalchemy import (
    CheckConstraint,
    Date,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
)
from sqlalchemy.dialects.postgresql import ARRAY, JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from igs_common.db.base import Base, IdMixin, TenantMixin, TimestampMixin
from igs_common.db.enums import (
    AccountHealth,
    AccountKind,
    AccountStatus,
    Direction,
    FactKind,
    FactSeverity,
    FactStatus,
    InteractionChannel,
    Sentiment,
    StakeholderRole,
    pg_enum,
)


class Account(IdMixin, TimestampMixin, TenantMixin, Base):
    __tablename__ = "accounts"
    __table_args__ = (
        Index("uq_accounts_tenant_name", "tenant_id", "name", unique=True),
        Index("ix_accounts_tenant_status_health", "tenant_id", "status", "health"),
    )

    name: Mapped[str] = mapped_column(Text)
    kind: Mapped[AccountKind] = mapped_column(pg_enum(AccountKind, "account_kind"))
    country: Mapped[str] = mapped_column(Text)
    state: Mapped[str | None] = mapped_column(Text)
    city: Mapped[str | None] = mapped_column(Text)
    sport_programs: Mapped[list[str]] = mapped_column(ARRAY(Text), server_default="{}")
    tier: Mapped[str | None] = mapped_column(Text)
    owner_user_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL")
    )
    status: Mapped[AccountStatus] = mapped_column(
        pg_enum(AccountStatus, "account_status"), server_default=AccountStatus.PROSPECT.value
    )
    health: Mapped[AccountHealth] = mapped_column(
        pg_enum(AccountHealth, "account_health"), server_default=AccountHealth.GREEN.value
    )


class Stakeholder(IdMixin, TimestampMixin, TenantMixin, Base):
    """Adults at the client. Players (minors) are never stakeholders and never stored here."""

    __tablename__ = "stakeholders"
    __table_args__ = (
        CheckConstraint("influence BETWEEN 1 AND 5", name="influence_range"),
        Index("ix_stakeholders_account", "account_id"),
        Index("ix_stakeholders_tenant_email", "tenant_id", "email"),
    )

    account_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("accounts.id", ondelete="CASCADE")
    )
    contact_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("contacts.id", ondelete="SET NULL")
    )
    name: Mapped[str] = mapped_column(Text)
    title: Mapped[str | None] = mapped_column(Text)
    role: Mapped[StakeholderRole] = mapped_column(pg_enum(StakeholderRole, "stakeholder_role"))
    influence: Mapped[int] = mapped_column(Integer, server_default="3")
    sentiment: Mapped[Sentiment] = mapped_column(
        pg_enum(Sentiment, "sentiment"), server_default=Sentiment.UNKNOWN.value
    )
    email: Mapped[str | None] = mapped_column(Text)
    phone: Mapped[str | None] = mapped_column(Text)
    preferred_channel: Mapped[InteractionChannel | None] = mapped_column(
        pg_enum(InteractionChannel, "interaction_channel")
    )
    last_contact_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    notes: Mapped[str | None] = mapped_column(Text)


class Interaction(IdMixin, TimestampMixin, TenantMixin, Base):
    """A touchpoint. `body` is the source text: chunked into document_chunks for the RAG."""

    __tablename__ = "interactions"
    __table_args__ = (
        Index("ix_interactions_account_occurred", "tenant_id", "account_id", "occurred_at"),
        Index("ix_interactions_stakeholder", "stakeholder_id"),
    )

    account_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("accounts.id", ondelete="CASCADE")
    )
    stakeholder_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("stakeholders.id", ondelete="SET NULL")
    )
    channel: Mapped[InteractionChannel] = mapped_column(
        pg_enum(InteractionChannel, "interaction_channel")
    )
    direction: Mapped[Direction] = mapped_column(pg_enum(Direction, "direction"))
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    subject: Mapped[str | None] = mapped_column(Text)
    body: Mapped[str] = mapped_column(Text)
    trip_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("trips.id", ondelete="SET NULL")
    )
    lead_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("leads.id", ondelete="SET NULL")
    )


class AccountFact(IdMixin, TimestampMixin, TenantMixin, Base):
    """LLM-extracted statement about an account. Always has a source interaction (provenance)."""

    __tablename__ = "account_facts"
    __table_args__ = (
        CheckConstraint("confidence BETWEEN 0 AND 1", name="confidence_range"),
        # "Current facts" = not superseded; the brief reads only these.
        Index(
            "ix_account_facts_current",
            "tenant_id",
            "account_id",
            "kind",
            postgresql_where="superseded_by IS NULL",
        ),
        Index("ix_account_facts_source", "source_interaction_id"),
    )

    account_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("accounts.id", ondelete="CASCADE")
    )
    kind: Mapped[FactKind] = mapped_column(pg_enum(FactKind, "fact_kind"))
    statement: Mapped[str] = mapped_column(Text)
    confidence: Mapped[float] = mapped_column(Float)
    source_interaction_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("interactions.id", ondelete="CASCADE")
    )
    valid_from: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    superseded_by: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("account_facts.id", ondelete="SET NULL")
    )
    # Risks only: drives the deterministic health rules (a high open risk → red).
    severity: Mapped[FactSeverity | None] = mapped_column(pg_enum(FactSeverity, "fact_severity"))
    # Commitments only: when the promise is due.
    due_date: Mapped[date | None] = mapped_column(Date)
    status: Mapped[FactStatus] = mapped_column(
        pg_enum(FactStatus, "fact_status"), server_default=FactStatus.OPEN.value
    )


class AccountBrief(IdMixin, TimestampMixin, TenantMixin, Base):
    """Cached LLM brief of an account. Regenerated only when `inputs_hash` changes."""

    __tablename__ = "account_briefs"
    __table_args__ = (
        Index(
            "uq_account_briefs_account_inputs",
            "tenant_id",
            "account_id",
            "inputs_hash",
            unique=True,
        ),
        Index("ix_account_briefs_account_created", "tenant_id", "account_id", "created_at"),
    )

    account_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("accounts.id", ondelete="CASCADE")
    )
    # sha256 over open fact ids/versions, stakeholder versions and the SQL status snapshot.
    inputs_hash: Mapped[str] = mapped_column(String(80))
    # {"text": "...", "citations": [{"n": 1, "interaction_id": "...", "span": [s, e]}], ...}
    brief: Mapped[dict[str, Any]] = mapped_column(JSONB)
    model: Mapped[str] = mapped_column(Text)
