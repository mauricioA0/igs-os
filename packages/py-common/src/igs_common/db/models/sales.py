import uuid
from datetime import date, datetime
from datetime import time as dt_time
from typing import Any

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    Date,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    Time,
    UniqueConstraint,
    text,
)
from sqlalchemy.dialects.postgresql import ARRAY, JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from igs_common.db.base import Base, IdMixin, TenantMixin, TimestampMixin
from igs_common.db.enums import (
    ActorType,
    Channel,
    Gender,
    IncidentSeverity,
    IncidentStatus,
    ItemKind,
    ItemSlot,
    ItemStatus,
    LeadSource,
    LeadStatus,
    MessageRole,
    Sport,
    TravelerRole,
    TripStatus,
    pg_enum,
)


class Contact(IdMixin, TimestampMixin, TenantMixin, Base):
    """A person who raises leads (coach, AD…). Exists before and across leads."""

    __tablename__ = "contacts"
    __table_args__ = (
        Index("ix_contacts_tenant_email", "tenant_id", "email"),
        Index("ix_contacts_account", "account_id"),
    )

    name: Mapped[str] = mapped_column(Text)
    email: Mapped[str | None] = mapped_column(Text)
    phone: Mapped[str | None] = mapped_column(Text)
    organization: Mapped[str | None] = mapped_column(Text)
    role: Mapped[str | None] = mapped_column(Text)
    account_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("accounts.id", ondelete="SET NULL")
    )


class Conversation(IdMixin, TimestampMixin, TenantMixin, Base):
    __tablename__ = "conversations"
    __table_args__ = (Index("ix_conversations_tenant_created", "tenant_id", "created_at"),)

    channel: Mapped[Channel] = mapped_column(pg_enum(Channel, "channel"))
    contact_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("contacts.id", ondelete="SET NULL")
    )
    is_simulation: Mapped[bool] = mapped_column(Boolean, server_default=text("false"))
    flow_execution_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("flow_executions.id", ondelete="SET NULL")
    )


class Message(IdMixin, TimestampMixin, TenantMixin, Base):
    """Append-only. `content` holds the provider's full content blocks, replayed verbatim."""

    __tablename__ = "messages"
    __table_args__ = (Index("ix_messages_conversation_created", "conversation_id", "created_at"),)

    conversation_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("conversations.id", ondelete="CASCADE")
    )
    role: Mapped[MessageRole] = mapped_column(pg_enum(MessageRole, "message_role"))
    content: Mapped[Any] = mapped_column(JSONB)


class Lead(IdMixin, TimestampMixin, TenantMixin, Base):
    __tablename__ = "leads"
    __table_args__ = (
        CheckConstraint("level_score BETWEEN 1 AND 10", name="level_score_range"),
        CheckConstraint("group_size > 0", name="group_size_positive"),
        Index("ix_leads_tenant_status_created", "tenant_id", "status", text("created_at DESC")),
        Index("ix_leads_account", "account_id"),
    )

    contact_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("contacts.id", ondelete="SET NULL")
    )
    account_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("accounts.id", ondelete="SET NULL")
    )
    conversation_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("conversations.id", ondelete="SET NULL")
    )
    sport: Mapped[Sport] = mapped_column(pg_enum(Sport, "sport"))
    gender: Mapped[Gender] = mapped_column(pg_enum(Gender, "gender"))
    age_group: Mapped[str] = mapped_column(Text)
    level_score: Mapped[int] = mapped_column(Integer)
    group_size: Mapped[int] = mapped_column(Integer)
    destination_country: Mapped[str] = mapped_column(Text)
    travel_start: Mapped[date] = mapped_column(Date)
    duration_days: Mapped[int] = mapped_column(Integer)
    budget_per_person_usd: Mapped[int | None] = mapped_column(Integer)
    goals: Mapped[str | None] = mapped_column(Text)
    status: Mapped[LeadStatus] = mapped_column(
        pg_enum(LeadStatus, "lead_status"), server_default=LeadStatus.NEW.value
    )
    source: Mapped[LeadSource] = mapped_column(
        pg_enum(LeadSource, "lead_source"), server_default=LeadSource.MANUAL.value
    )
    lost_reason: Mapped[str | None] = mapped_column(Text)


class LeadIntake(IdMixin, TimestampMixin, TenantMixin, Base):
    """One inbound inquiry (site form or forwarded email) before and after it becomes a lead.

    Holds what the coach actually wrote, what was extracted from it (unknowns stay null), the
    score and its reasons, and the 1-business-day response clock. A lead is created only when
    every field the lead model requires is known; until then the intake asks for the rest.
    """

    __tablename__ = "lead_intakes"
    __table_args__ = (
        CheckConstraint("channel IN ('form', 'email')", name="channel_known"),
        CheckConstraint("status IN ('open', 'lead_created', 'spam')", name="status_known"),
        CheckConstraint(
            "relationship IN ('new', 'known_contact', 'returning_customer', 'referral')",
            name="relationship_known",
        ),
        Index("uq_lead_intakes_tenant_dedupe", "tenant_id", "dedupe_key", unique=True),
        Index("ix_lead_intakes_tenant_status_due", "tenant_id", "status", "sla_due_at"),
        Index("ix_lead_intakes_contact", "contact_id"),
    )

    channel: Mapped[str] = mapped_column(Text)
    status: Mapped[str] = mapped_column(Text, server_default="open")
    # Form submission hash or email Message-ID: a resubmit never creates a second intake.
    dedupe_key: Mapped[str] = mapped_column(Text)
    relationship: Mapped[str] = mapped_column(Text, server_default="new")
    contact_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("contacts.id", ondelete="SET NULL")
    )
    account_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("accounts.id", ondelete="SET NULL")
    )
    lead_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("leads.id", ondelete="SET NULL")
    )
    approval_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("approvals.id", ondelete="SET NULL")
    )
    # The fields as submitted (form) or the parsed headers (email); the text the coach wrote.
    submitted: Mapped[dict[str, Any]] = mapped_column(JSONB, server_default="{}")
    body_text: Mapped[str] = mapped_column(Text, server_default="")
    extracted: Mapped[dict[str, Any]] = mapped_column(JSONB, server_default="{}")
    missing: Mapped[list[str]] = mapped_column(ARRAY(Text), server_default="{}")
    score: Mapped[int] = mapped_column(Integer, server_default="0")
    score_reasons: Mapped[list[Any]] = mapped_column(JSONB, server_default="[]")
    extraction_model: Mapped[str | None] = mapped_column(Text)
    received_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    sla_due_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    first_response_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class Trip(IdMixin, TimestampMixin, TenantMixin, Base):
    __tablename__ = "trips"
    __table_args__ = (
        CheckConstraint("end_date >= start_date", name="dates_ordered"),
        Index("ix_trips_tenant_status_start", "tenant_id", "status", "start_date"),
        Index("ix_trips_lead", "lead_id"),
        Index("ix_trips_account", "account_id"),
        CheckConstraint("travelers IS NULL OR travelers > 0", name="travelers_positive"),
    )

    lead_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("leads.id", ondelete="SET NULL")
    )
    account_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("accounts.id", ondelete="SET NULL")
    )
    code: Mapped[str | None] = mapped_column(Text)
    title: Mapped[str] = mapped_column(Text)
    city: Mapped[str] = mapped_column(Text)
    country: Mapped[str] = mapped_column(Text)
    start_date: Mapped[date] = mapped_column(Date)
    end_date: Mapped[date] = mapped_column(Date)
    status: Mapped[TripStatus] = mapped_column(
        pg_enum(TripStatus, "trip_status"), server_default=TripStatus.DRAFT.value
    )
    price_per_person_usd: Mapped[int] = mapped_column(Integer)
    summary: Mapped[str] = mapped_column(Text, server_default="")
    # Snapshot of the quote breakdown so a proposal never changes under the coach.
    pricing: Mapped[dict[str, Any]] = mapped_column(JSONB, server_default="{}")
    travelers: Mapped[int | None] = mapped_column(Integer)
    owner_user_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL")
    )


class Traveler(IdMixin, TimestampMixin, TenantMixin, Base):
    """One person on a trip's roster: players, staff and parents.

    Minors are data-minimized: only a birth year (no full date) and never their own email or
    phone — trip communication goes to the adults (enforced by `minor_no_contact`).
    """

    __tablename__ = "travelers"
    __table_args__ = (
        CheckConstraint(
            "NOT is_minor OR (email IS NULL AND phone IS NULL)", name="minor_no_contact"
        ),
        CheckConstraint(
            "birth_year IS NULL OR birth_year BETWEEN 1900 AND 2100", name="birth_year_range"
        ),
        Index("ix_travelers_tenant_trip", "tenant_id", "trip_id"),
    )

    trip_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("trips.id", ondelete="CASCADE")
    )
    full_name: Mapped[str] = mapped_column(Text)
    role: Mapped[TravelerRole] = mapped_column(pg_enum(TravelerRole, "traveler_role"))
    is_minor: Mapped[bool] = mapped_column(Boolean, server_default=text("false"))
    birth_year: Mapped[int | None] = mapped_column(Integer)
    email: Mapped[str | None] = mapped_column(Text)
    phone: Mapped[str | None] = mapped_column(Text)


class TravelerDocument(IdMixin, TimestampMixin, TenantMixin, Base):
    """Collection status of one pre-departure requirement for one traveler.

    Status only, never the document: no scans, no passport numbers. Passports keep their issue
    and expiry dates (`valid_from` / `valid_until`) because the entry rules are computed from them.
    """

    __tablename__ = "traveler_documents"
    __table_args__ = (
        UniqueConstraint("traveler_id", "requirement"),
        CheckConstraint(
            "status IN ('missing', 'requested', 'received', 'verified', 'not_applicable')",
            name="status_known",
        ),
        CheckConstraint(
            "valid_until IS NULL OR valid_from IS NULL OR valid_until >= valid_from",
            name="validity_ordered",
        ),
        Index("ix_traveler_documents_tenant_traveler", "tenant_id", "traveler_id"),
    )

    traveler_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("travelers.id", ondelete="CASCADE")
    )
    requirement: Mapped[str] = mapped_column(String(40))
    status: Mapped[str] = mapped_column(String(20), server_default="missing")
    valid_from: Mapped[date | None] = mapped_column(Date)
    valid_until: Mapped[date | None] = mapped_column(Date)
    note: Mapped[str | None] = mapped_column(Text)
    updated_by: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL")
    )


class TripItem(IdMixin, TimestampMixin, TenantMixin, Base):
    __tablename__ = "trip_items"
    __table_args__ = (
        CheckConstraint("day >= 1", name="day_positive"),
        Index("ix_trip_items_trip_day_slot", "trip_id", "day", "slot"),
        Index(
            "ix_trip_items_tenant_open",
            "tenant_id",
            "status",
            postgresql_where="status IN ('pending', 'requested')",
        ),
    )

    trip_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("trips.id", ondelete="CASCADE")
    )
    day: Mapped[int] = mapped_column(Integer)
    slot: Mapped[ItemSlot] = mapped_column(pg_enum(ItemSlot, "item_slot"))
    kind: Mapped[ItemKind] = mapped_column(pg_enum(ItemKind, "item_kind"))
    title: Mapped[str] = mapped_column(Text)
    opponent_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("opponents.id", ondelete="SET NULL")
    )
    experience_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("experiences.id", ondelete="SET NULL")
    )
    provider_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("providers.id", ondelete="SET NULL")
    )
    status: Mapped[ItemStatus] = mapped_column(
        pg_enum(ItemStatus, "item_status"), server_default=ItemStatus.PENDING.value
    )
    notes: Mapped[str | None] = mapped_column(Text)
    # Local time at the destination (trip timezone), e.g. 16:00 kick-off.
    time: Mapped[dt_time | None] = mapped_column(Time)
    # Ops-facing warning shown on the timeline ("Falta confirmar árbitro").
    alert: Mapped[str | None] = mapped_column(Text)
    requested_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    confirmed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    # Outcome of a completed item, e.g. {"score": "2-1", "report": "..."} for a match.
    result: Mapped[dict[str, Any] | None] = mapped_column(JSONB)


class Incident(IdMixin, TimestampMixin, TenantMixin, Base):
    """On-tour issue (injury, late bus, cancelled match)."""

    __tablename__ = "incidents"
    __table_args__ = (
        Index("ix_incidents_tenant_status_severity", "tenant_id", "status", "severity"),
        Index("ix_incidents_trip", "trip_id"),
    )

    trip_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("trips.id", ondelete="CASCADE")
    )
    trip_item_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("trip_items.id", ondelete="SET NULL")
    )
    severity: Mapped[IncidentSeverity] = mapped_column(
        pg_enum(IncidentSeverity, "incident_severity")
    )
    category: Mapped[str] = mapped_column(Text)
    title: Mapped[str] = mapped_column(Text)
    description: Mapped[str] = mapped_column(Text, server_default="")
    status: Mapped[IncidentStatus] = mapped_column(
        pg_enum(IncidentStatus, "incident_status"), server_default=IncidentStatus.OPEN.value
    )
    reported_by_type: Mapped[ActorType] = mapped_column(pg_enum(ActorType, "actor_type"))
    reported_by_id: Mapped[str | None] = mapped_column(Text)
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
