"""Domain enums. Values match the Postgres enums in docs/architecture/data-model.md."""

from enum import StrEnum


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


class Slot(StrEnum):
    MORNING = "morning"
    AFTERNOON = "afternoon"
    EVENING = "evening"


SLOT_ORDER: dict[Slot, int] = {Slot.MORNING: 0, Slot.AFTERNOON: 1, Slot.EVENING: 2}


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


class ItemStatus(StrEnum):
    PENDING = "pending"
    REQUESTED = "requested"
    CONFIRMED = "confirmed"
    COMPLETED = "completed"
    CANCELLED = "cancelled"


class LeadStatus(StrEnum):
    NEW = "new"
    QUALIFIED = "qualified"
    PROPOSAL_SENT = "proposal_sent"
    WON = "won"
    LOST = "lost"


class TripStatus(StrEnum):
    DRAFT = "draft"
    PROPOSED = "proposed"
    CONFIRMED = "confirmed"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    CANCELLED = "cancelled"


class ApprovalStatus(StrEnum):
    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"
    EXPIRED = "expired"


class ProviderKind(StrEnum):
    HOTEL = "hotel"
    TRANSPORT = "transport"
    VENUE = "venue"
    REFEREE = "referee"
    GUIDE = "guide"
    CLUB = "club"
