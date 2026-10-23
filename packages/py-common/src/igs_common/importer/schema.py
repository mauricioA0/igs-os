"""What an import file may contain: one `EntitySpec` per sheet, one `FieldSpec` per column.

The specs are the single source of truth for the templates (docs/import/templates), the header
matcher, the LLM column mapper and validation. Aliases cover the headers ops actually uses in
their spreadsheets (English and Spanish); anything else goes through the mapper or is reported.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum

from igs_common.db.enums import (
    AccountKind,
    AccountStatus,
    InteractionChannel,
    ProviderKind,
    Sentiment,
    StakeholderRole,
    TravelerRole,
    TripStatus,
)


class FieldType(StrEnum):
    TEXT = "text"
    EMAIL = "email"
    INT = "int"
    MONEY = "money"  # whole US dollars; "US$ 2,280" → 2280
    DATE = "date"
    BOOL = "bool"
    ENUM = "enum"
    LIST = "list"  # comma/semicolon separated


class Entity(StrEnum):
    ACCOUNTS = "accounts"
    STAKEHOLDERS = "stakeholders"
    PROVIDERS = "providers"
    TRIPS = "trips"
    TRAVELERS = "travelers"
    PAYMENTS = "payments"


class PaymentKind(StrEnum):
    """IGS terms: US$95 enrollment fee, US$500 installments, balance 110 days before departure."""

    ENROLLMENT_FEE = "enrollment_fee"
    INSTALLMENT = "installment"
    BALANCE = "balance"
    OTHER = "other"


@dataclass(frozen=True)
class FieldSpec:
    name: str
    type: FieldType
    description: str
    required: bool = False
    aliases: tuple[str, ...] = ()
    choices: tuple[str, ...] = ()
    # Spreadsheet spellings of enum values ("Universidad" → "university").
    value_aliases: dict[str, str] = field(default_factory=dict)
    example: str = ""


@dataclass(frozen=True)
class EntitySpec:
    entity: Entity
    description: str
    fields: tuple[FieldSpec, ...]
    # Columns that identify a row across imports (dedupe + idempotent upsert).
    key: tuple[str, ...]
    sheet_aliases: tuple[str, ...] = ()
    # Columns we refuse to store even if present (minors' personal data).
    forbidden: tuple[str, ...] = ()

    def field(self, name: str) -> FieldSpec:
        return next(f for f in self.fields if f.name == name)

    @property
    def field_names(self) -> tuple[str, ...]:
        return tuple(f.name for f in self.fields)


def _choices(enum: type[StrEnum]) -> tuple[str, ...]:
    return tuple(m.value for m in enum)


ACCOUNT_KIND_ALIASES = {
    "universidad": "university",
    "college": "university",
    "colegio": "high_school",
    "school": "high_school",
    "private_school": "high_school",
    "highschool": "high_school",
    "club": "club",
    "familia": "family_group",
    "family": "family_group",
    "familias": "family_group",
}

STAKEHOLDER_ROLE_ALIASES = {
    "head_coach": "coach",
    "entrenador": "coach",
    "entrenadora": "coach",
    "assistant": "assistant_coach",
    "ad": "athletic_director",
    "director_deportivo": "athletic_director",
    "finanzas": "finance",
    "compras": "finance",
    "procurement": "finance",
    "coordinator": "travel_coordinator",
    "decision": "decision_maker",
    "parent": "parent_liaison",
    "padre": "parent_liaison",
    "madre": "parent_liaison",
}

SPECS: dict[Entity, EntitySpec] = {
    Entity.ACCOUNTS: EntitySpec(
        Entity.ACCOUNTS,
        "Clients: universities, clubs, schools and family groups.",
        (
            FieldSpec(
                "name",
                FieldType.TEXT,
                "Organization name, unique",
                required=True,
                aliases=("account", "organization", "client", "cliente", "institucion", "nombre"),
                example="Lakeshore University",
            ),
            FieldSpec(
                "kind",
                FieldType.ENUM,
                "Type of client",
                required=True,
                aliases=("type", "tipo"),
                choices=_choices(AccountKind),
                value_aliases=ACCOUNT_KIND_ALIASES,
                example="university",
            ),
            FieldSpec(
                "country",
                FieldType.TEXT,
                "Country",
                required=True,
                aliases=("pais",),
                example="USA",
            ),
            FieldSpec("state", FieldType.TEXT, "State/province", aliases=("provincia", "estado")),
            FieldSpec("city", FieldType.TEXT, "City", aliases=("ciudad",), example="Chicago"),
            FieldSpec(
                "sport_programs",
                FieldType.LIST,
                "Programs, comma separated",
                aliases=("sports", "programs", "deportes", "programas"),
                example="women's soccer, men's rugby",
            ),
            FieldSpec("tier", FieldType.TEXT, "D1/D2/D3/NAIA/ECNL…", aliases=("division", "nivel")),
            FieldSpec(
                "status",
                FieldType.ENUM,
                "Relationship status",
                aliases=("estado_cliente",),
                choices=_choices(AccountStatus),
                value_aliases={"cliente": "active", "activo": "active", "lead": "prospect"},
                example="active",
            ),
        ),
        key=("name",),
        sheet_aliases=("clients", "clientes", "cuentas", "organizations"),
    ),
    Entity.STAKEHOLDERS: EntitySpec(
        Entity.STAKEHOLDERS,
        "Adults at each client (coaches, AD, finance). Never players.",
        (
            FieldSpec(
                "account_name",
                FieldType.TEXT,
                "Client name as in the accounts sheet",
                required=True,
                aliases=("account", "organization", "client", "cliente", "institucion"),
                example="Lakeshore University",
            ),
            FieldSpec(
                "name",
                FieldType.TEXT,
                "Full name",
                required=True,
                aliases=("contact", "contacto", "nombre", "full_name"),
                example="Dana Whitfield",
            ),
            FieldSpec(
                "title", FieldType.TEXT, "Job title", aliases=("cargo", "puesto", "position")
            ),
            FieldSpec(
                "role",
                FieldType.ENUM,
                "Role in the buying decision",
                required=True,
                aliases=("rol",),
                choices=_choices(StakeholderRole),
                value_aliases=STAKEHOLDER_ROLE_ALIASES,
                example="coach",
            ),
            FieldSpec(
                "email",
                FieldType.EMAIL,
                "Email",
                aliases=("mail", "correo", "e_mail"),
                example="dana@lakeshore.example",
            ),
            FieldSpec("phone", FieldType.TEXT, "Phone", aliases=("telefono", "tel", "whatsapp")),
            FieldSpec(
                "influence",
                FieldType.INT,
                "1 (low) to 5 (decides)",
                aliases=("influencia", "weight"),
                example="5",
            ),
            FieldSpec(
                "sentiment",
                FieldType.ENUM,
                "How they feel about IGS",
                aliases=("sentimiento",),
                choices=_choices(Sentiment),
                value_aliases={"positivo": "positive", "neutro": "neutral", "negativo": "negative"},
            ),
            FieldSpec(
                "preferred_channel",
                FieldType.ENUM,
                "Preferred channel",
                aliases=("channel", "canal"),
                choices=_choices(InteractionChannel),
                value_aliases={"mail": "email", "llamada": "call", "wa": "whatsapp"},
            ),
            FieldSpec("notes", FieldType.TEXT, "Notes", aliases=("notas", "comentarios")),
        ),
        key=("account_name", "email", "name"),
        sheet_aliases=("contacts", "contactos", "people", "personas"),
    ),
    Entity.PROVIDERS: EntitySpec(
        Entity.PROVIDERS,
        "Hotels, buses, venues, referees, guides and rival clubs.",
        (
            FieldSpec(
                "name",
                FieldType.TEXT,
                "Provider name",
                required=True,
                aliases=("proveedor", "nombre", "provider"),
                example="Hotel Palermo Soho",
            ),
            FieldSpec(
                "kind",
                FieldType.ENUM,
                "Provider type",
                required=True,
                aliases=("type", "tipo", "rubro"),
                choices=_choices(ProviderKind),
                value_aliases={
                    "bus": "transport",
                    "micro": "transport",
                    "transporte": "transport",
                    "cancha": "venue",
                    "estadio": "venue",
                    "arbitro": "referee",
                    "guia": "guide",
                    "club_rival": "club",
                },
                example="hotel",
            ),
            FieldSpec(
                "city",
                FieldType.TEXT,
                "City",
                required=True,
                aliases=("ciudad",),
                example="Buenos Aires",
            ),
            FieldSpec(
                "country",
                FieldType.TEXT,
                "Country",
                required=True,
                aliases=("pais",),
                example="Argentina",
            ),
            FieldSpec(
                "contact",
                FieldType.TEXT,
                "Who to call (name, phone or email)",
                required=True,
                aliases=("contacto", "email", "phone", "telefono"),
                example="reservas@hotel.example",
            ),
            FieldSpec(
                "unit_price_usd",
                FieldType.MONEY,
                "Price per unit in USD",
                required=True,
                aliases=("price", "precio", "price_usd", "tarifa", "costo"),
                example="95",
            ),
            FieldSpec(
                "unit",
                FieldType.TEXT,
                "Unit of the price (night, day, match…)",
                required=True,
                aliases=("unidad", "per"),
                example="room night",
            ),
        ),
        key=("name", "kind", "city"),
        sheet_aliases=("proveedores", "suppliers", "vendors"),
    ),
    Entity.TRIPS: EntitySpec(
        Entity.TRIPS,
        "Tours, one row per trip. `code` is how payments and travelers refer to it.",
        (
            FieldSpec(
                "code",
                FieldType.TEXT,
                "Trip code, unique (e.g. IGS-2711)",
                required=True,
                aliases=("trip_code", "codigo", "id", "tour_code", "file"),
                example="IGS-2711",
            ),
            FieldSpec(
                "account_name",
                FieldType.TEXT,
                "Client name as in the accounts sheet",
                aliases=("account", "client", "cliente", "organization"),
                example="Lakeshore University",
            ),
            FieldSpec(
                "title",
                FieldType.TEXT,
                "Trip title",
                required=True,
                aliases=("titulo", "nombre", "name", "tour"),
                example="Women's Soccer — Buenos Aires Spring Tour",
            ),
            FieldSpec(
                "city",
                FieldType.TEXT,
                "Main city",
                required=True,
                aliases=("ciudad", "destination", "destino"),
                example="Buenos Aires",
            ),
            FieldSpec(
                "country",
                FieldType.TEXT,
                "Country",
                required=True,
                aliases=("pais",),
                example="Argentina",
            ),
            FieldSpec(
                "start_date",
                FieldType.DATE,
                "Arrival date",
                required=True,
                aliases=("start", "inicio", "salida", "departure", "fecha_inicio"),
                example="2027-03-12",
            ),
            FieldSpec(
                "end_date",
                FieldType.DATE,
                "Return date",
                required=True,
                aliases=("end", "fin", "regreso", "return", "fecha_fin"),
                example="2027-03-21",
            ),
            FieldSpec(
                "status",
                FieldType.ENUM,
                "Trip status",
                aliases=("estado",),
                choices=_choices(TripStatus),
                value_aliases={
                    "borrador": "draft",
                    "cotizado": "proposed",
                    "propuesta": "proposed",
                    "confirmado": "confirmed",
                    "en_curso": "in_progress",
                    "terminado": "completed",
                    "cancelado": "cancelled",
                },
                example="confirmed",
            ),
            FieldSpec(
                "price_per_person_usd",
                FieldType.MONEY,
                "Price per traveler in USD",
                required=True,
                aliases=("price", "precio", "price_pp", "precio_por_persona"),
                example="2890",
            ),
            FieldSpec(
                "travelers",
                FieldType.INT,
                "Expected travelers (the travelers sheet overrides it)",
                aliases=("pax", "viajeros", "group_size"),
                example="24",
            ),
        ),
        key=("code",),
        sheet_aliases=("tours", "viajes", "giras"),
    ),
    Entity.TRAVELERS: EntitySpec(
        Entity.TRAVELERS,
        "Roster per trip. Minors: birth year only, and no email/phone of their own.",
        (
            FieldSpec(
                "trip_code",
                FieldType.TEXT,
                "Trip code as in the trips sheet",
                required=True,
                aliases=("trip", "code", "codigo", "viaje", "tour"),
                example="IGS-2711",
            ),
            FieldSpec(
                "full_name",
                FieldType.TEXT,
                "Full name as on the passport",
                required=True,
                aliases=("name", "nombre", "nombre_completo", "traveler", "pasajero"),
                example="Jamie Rivera",
            ),
            FieldSpec(
                "role",
                FieldType.ENUM,
                "player, staff or parent",
                required=True,
                aliases=("type", "tipo", "rol"),
                choices=_choices(TravelerRole),
                value_aliases={
                    "jugador": "player",
                    "jugadora": "player",
                    "athlete": "player",
                    "coach": "staff",
                    "entrenador": "staff",
                    "entrenadora": "staff",
                    "chaperone": "parent",
                    "padre": "parent",
                    "madre": "parent",
                    "acompanante": "parent",
                },
                example="player",
            ),
            FieldSpec(
                "is_minor",
                FieldType.BOOL,
                "Under 18 at departure",
                aliases=("minor", "menor", "under_18"),
                example="yes",
            ),
            FieldSpec(
                "birth_year",
                FieldType.INT,
                "Year of birth (only the year)",
                aliases=("year_of_birth", "ano_nacimiento", "anio_nacimiento", "clase"),
                example="2009",
            ),
            FieldSpec(
                "email",
                FieldType.EMAIL,
                "Email (adults only)",
                aliases=("mail", "correo"),
                example="",
            ),
            FieldSpec(
                "phone",
                FieldType.TEXT,
                "Phone/WhatsApp (adults only)",
                aliases=("telefono", "tel", "whatsapp", "celular"),
                example="",
            ),
        ),
        key=("trip_code", "full_name"),
        sheet_aliases=("roster", "pasajeros", "viajeros", "plantel"),
        # Not needed to run a tour from IGS OS; kept out of the database on purpose.
        forbidden=(
            "birthdate",
            "date_of_birth",
            "dob",
            "fecha_de_nacimiento",
            "passport",
            "passport_number",
            "pasaporte",
            "dni",
            "ssn",
            "medical",
            "allergies",
            "alergias",
        ),
    ),
    Entity.PAYMENTS: EntitySpec(
        Entity.PAYMENTS,
        "Payment schedule and receipts per trip (enrollment fees, installments, balance).",
        (
            FieldSpec(
                "trip_code",
                FieldType.TEXT,
                "Trip code as in the trips sheet",
                required=True,
                aliases=("trip", "code", "codigo", "viaje", "tour"),
                example="IGS-2711",
            ),
            FieldSpec(
                "payment_ref",
                FieldType.TEXT,
                "Invoice/receipt number, unique per trip",
                required=True,
                aliases=("ref", "invoice", "factura", "recibo", "comprobante", "id"),
                example="INV-1042",
            ),
            FieldSpec(
                "kind",
                FieldType.ENUM,
                "enrollment_fee, installment, balance or other",
                required=True,
                aliases=("type", "tipo", "concepto", "concept"),
                choices=_choices(PaymentKind),
                value_aliases={
                    "enrollment": "enrollment_fee",
                    "inscripcion": "enrollment_fee",
                    "fee": "enrollment_fee",
                    "cuota": "installment",
                    "deposit": "installment",
                    "sena": "installment",
                    "saldo": "balance",
                    "final": "balance",
                },
                example="enrollment_fee",
            ),
            FieldSpec(
                "amount_usd",
                FieldType.MONEY,
                "Amount in USD",
                required=True,
                aliases=("amount", "monto", "importe", "total"),
                example="2280",
            ),
            FieldSpec(
                "due_date",
                FieldType.DATE,
                "Due date",
                required=True,
                aliases=("due", "vencimiento", "vence"),
                example="2026-10-15",
            ),
            FieldSpec(
                "paid_at",
                FieldType.DATE,
                "Date it was received (empty = not paid)",
                aliases=("paid", "pagado", "fecha_pago", "cobrado"),
                example="",
            ),
        ),
        key=("trip_code", "payment_ref"),
        sheet_aliases=("pagos", "cobros", "invoices", "facturas"),
    ),
}

# Apply order: referenced entities first.
APPLY_ORDER = (
    Entity.ACCOUNTS,
    Entity.STAKEHOLDERS,
    Entity.PROVIDERS,
    Entity.TRIPS,
    Entity.TRAVELERS,
    Entity.PAYMENTS,
)
