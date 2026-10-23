"""Lead score 0–100 with every point explained (ops reads the reasons, in Spanish).

Rules, not a model: sales has to be able to argue with each line. The weights encode what IGS
publishes about its business: groups of 20–35, planning 12–18 months ahead, returning customers
and referrals as measured channels, and several stakeholders where the person writing isn't
always the one who decides.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import Any

from .form import DECISION_MAKERS

BASE = 30
FREE_MAIL = frozenset(
    {"gmail.com", "yahoo.com", "hotmail.com", "outlook.com", "icloud.com", "aol.com", "live.com"}
)


@dataclass(frozen=True)
class Reason:
    points: int
    reason: str

    def to_json(self) -> dict[str, Any]:
        return {"points": self.points, "reason": self.reason}


@dataclass(frozen=True)
class Score:
    value: int
    reasons: tuple[Reason, ...]

    def to_json(self) -> list[dict[str, Any]]:
        return [r.to_json() for r in self.reasons]


def score_inquiry(
    *,
    values: dict[str, Any],
    relationship: str,
    role: str | None,
    email: str,
    travel_window: tuple[date, date] | None,
    today: date,
    missing: list[str],
    notes: list[Reason] | None = None,
) -> Score:
    reasons: list[Reason] = list(notes or [])

    def add(points: int, reason: str) -> None:
        reasons.append(Reason(points, reason))

    if relationship == "returning_customer":
        add(25, "Cliente que ya viajó con IGS")
    elif relationship == "known_contact":
        add(10, "Contacto o cuenta que ya conocemos")
    elif relationship == "referral":
        add(10, "Llegó por recomendación")

    if role in DECISION_MAKERS:
        add(15, f"Escribe quien decide o firma ({role})")
    elif role == "Head Coach":
        add(10, "Escribe el head coach")
    elif role == "Assistant Coach":
        add(0, "Escribe un asistente: hay que llegar a quien decide")

    start = values.get("travel_start")
    earliest = start if isinstance(start, date) else (travel_window[0] if travel_window else None)
    if earliest is None:
        add(0, "Ventana de viaje sin fecha: preguntarla")
    else:
        months = (earliest.year - today.year) * 12 + earliest.month - today.month
        if months < 0:
            add(-15, "La fecha indicada ya pasó: confirmar")
        elif months < 3:
            add(-10, f"Viaja en {months} meses: poco margen para rivales y hotel")
        elif months < 6:
            add(5, f"Viaja en {months} meses: ajustado pero posible")
        elif months <= 18:
            add(15, f"Viaja en {months} meses: dentro de la ventana ideal (6–18)")
        else:
            add(5, f"Viaja en {months} meses: lejos, nutrir hasta que haya presupuesto")

    size = values.get("group_size")
    if isinstance(size, int):
        if 20 <= size <= 35:
            add(10, f"{size} viajeros: tamaño típico de gira")
        elif 12 <= size < 20 or 35 < size <= 50:
            add(5, f"{size} viajeros")
        else:
            add(-5, f"{size} viajeros: fuera del rango habitual")

    if values.get("budget_per_person_usd") is not None:
        add(5, "Dijo un presupuesto por persona")

    domain = email.rsplit("@", 1)[-1].lower()
    if domain.endswith(".edu") or domain.endswith(".k12.us"):
        add(5, "Mail institucional (.edu)")
    elif domain in FREE_MAIL:
        add(0, "Mail personal: confirmar la institución")

    known = 8 - len(missing)
    if known:
        add(known, f"Ya sabemos {known} de 8 datos para cotizar")

    value = max(0, min(100, BASE + sum(r.points for r in reasons)))
    return Score(value=value, reasons=tuple(reasons))
