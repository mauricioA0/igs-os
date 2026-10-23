"""Postgres native enums, mirrored as Python StrEnums.

New values are added with an `ALTER TYPE ... ADD VALUE` migration, never by editing an old one.
"""

from enum import StrEnum

from sqlalchemy import Enum as SAEnum


def pg_enum(enum_cls: type[StrEnum], name: str) -> SAEnum:
    """Native Postgres enum that stores the StrEnum *values* (not member names)."""
    return SAEnum(
        enum_cls,
        name=name,
        values_callable=lambda cls: [m.value for m in cls],
        validate_strings=True,
    )


class UserRole(StrEnum):
    OWNER = "owner"
    OPS = "ops"
    SALES = "sales"
    VIEWER = "viewer"


class Sport(StrEnum):
    SOCCER = "soccer"
    RUGBY = "rugby"
    FIELD_HOCKEY = "field_hockey"
    VOLLEYBALL = "volleyball"
    BASKETBALL = "basketball"


class Gender(StrEnum):
    MEN = "men"
    WOMEN = "women"
    MIXED = "mixed"


class ProviderKind(StrEnum):
    HOTEL = "hotel"
    TRANSPORT = "transport"
    VENUE = "venue"
    REFEREE = "referee"
    GUIDE = "guide"
    CLUB = "club"


class LeadStatus(StrEnum):
    NEW = "new"
    QUALIFIED = "qualified"
    PROPOSAL_SENT = "proposal_sent"
    WON = "won"
    LOST = "lost"


class LeadSource(StrEnum):
    CHAT = "chat"
    WEBHOOK = "webhook"
    MANUAL = "manual"
    FLOW = "flow"


class TripStatus(StrEnum):
    DRAFT = "draft"
    PROPOSED = "proposed"
    CONFIRMED = "confirmed"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    CANCELLED = "cancelled"


class TravelerRole(StrEnum):
    PLAYER = "player"
    STAFF = "staff"
    PARENT = "parent"


class ItemKind(StrEnum):
    ARRIVAL = "arrival"
    DEPARTURE = "departure"
    MATCH = "match"
    TRAINING = "training"
    EXPERIENCE = "experience"
    FREE = "free"


class ItemSlot(StrEnum):
    MORNING = "morning"
    AFTERNOON = "afternoon"
    EVENING = "evening"


class ItemStatus(StrEnum):
    PENDING = "pending"
    REQUESTED = "requested"
    CONFIRMED = "confirmed"
    COMPLETED = "completed"
    CANCELLED = "cancelled"


class Channel(StrEnum):
    WEB = "web"
    WHATSAPP = "whatsapp"
    EMAIL = "email"
    MCP = "mcp"


class MessageRole(StrEnum):
    USER = "user"
    ASSISTANT = "assistant"


class IncidentSeverity(StrEnum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class IncidentStatus(StrEnum):
    OPEN = "open"
    MITIGATING = "mitigating"
    RESOLVED = "resolved"


# ── Account 360 ────────────────────────────────────────────────────────────


class AccountKind(StrEnum):
    UNIVERSITY = "university"
    CLUB = "club"
    HIGH_SCHOOL = "high_school"
    FAMILY_GROUP = "family_group"


class AccountStatus(StrEnum):
    PROSPECT = "prospect"
    ACTIVE = "active"
    PAST = "past"
    CHURNED = "churned"


class AccountHealth(StrEnum):
    GREEN = "green"
    AMBER = "amber"
    RED = "red"


class StakeholderRole(StrEnum):
    DECISION_MAKER = "decision_maker"
    CHAMPION = "champion"
    COACH = "coach"
    ASSISTANT_COACH = "assistant_coach"
    ATHLETIC_DIRECTOR = "athletic_director"
    COMPLIANCE = "compliance"
    TRAVEL_COORDINATOR = "travel_coordinator"
    FINANCE = "finance"
    PARENT_LIAISON = "parent_liaison"
    OTHER = "other"


class Sentiment(StrEnum):
    POSITIVE = "positive"
    NEUTRAL = "neutral"
    NEGATIVE = "negative"
    UNKNOWN = "unknown"


class InteractionChannel(StrEnum):
    EMAIL = "email"
    CALL = "call"
    MEETING = "meeting"
    CHAT = "chat"
    WHATSAPP = "whatsapp"
    NOTE = "note"


class Direction(StrEnum):
    INBOUND = "inbound"
    OUTBOUND = "outbound"
    INTERNAL = "internal"


class FactKind(StrEnum):
    STATUS = "status"
    COMMITMENT = "commitment"
    RISK = "risk"
    PREFERENCE = "preference"
    BUDGET = "budget"
    DECISION = "decision"


class FactSeverity(StrEnum):
    """Only meaningful for `risk` facts (drives account health)."""

    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


class FactStatus(StrEnum):
    """Lifecycle of commitments and risks; other kinds stay `open` until superseded."""

    OPEN = "open"
    DONE = "done"
    DROPPED = "dropped"


# ── Flows ──────────────────────────────────────────────────────────────────


class TriggerKind(StrEnum):
    CHAT = "chat"
    WEBHOOK = "webhook"
    SCHEDULE = "schedule"
    EVENT = "event"
    MANUAL = "manual"


class ExecutionStatus(StrEnum):
    RUNNING = "running"
    WAITING = "waiting"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    CANCELLED = "cancelled"


class NodeRunStatus(StrEnum):
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    SKIPPED = "skipped"
    WAITING = "waiting"


class ApprovalStatus(StrEnum):
    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"
    EXPIRED = "expired"
    SUPERSEDED = "superseded"


class ToolClass(StrEnum):
    """Risk class of a tool or proposed action (security.md §tool classes)."""

    READ = "read"
    INTERNAL_WRITE = "internal_write"
    EXTERNAL = "external"


# ── Agents, documents, audit ──────────────────────────────────────────────


class AgentSurface(StrEnum):
    CHAT = "chat"
    FLOW = "flow"
    MCP = "mcp"
    COPILOT = "copilot"
    EVAL = "eval"


class DocumentStatus(StrEnum):
    PENDING = "pending"
    INGESTING = "ingesting"
    READY = "ready"
    FAILED = "failed"


class IngestionStatus(StrEnum):
    QUEUED = "queued"
    PARSING = "parsing"
    CHUNKING = "chunking"
    EMBEDDING = "embedding"
    INDEXING = "indexing"
    SUCCEEDED = "succeeded"
    FAILED = "failed"


class ActorType(StrEnum):
    USER = "user"
    AGENT = "agent"
    FLOW = "flow"
    API_KEY = "api_key"
    SYSTEM = "system"
