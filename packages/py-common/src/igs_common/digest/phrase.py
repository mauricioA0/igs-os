"""The only model-written part of the digest: a 2–3 sentence opening, checked against the facts.

If the model writes a number the facts don't contain, it gets one retry with the offending
tokens; after that (or on any provider error) the deterministic template is used. The digest
never waits on, or depends on, the model.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Literal

import structlog
from pydantic import BaseModel, Field

from igs_common.llm import GenerateOptions, LLMClient, LLMError, Message, Role

from .numbers import allowed_numbers, check_numbers
from .types import DigestFacts

log = structlog.get_logger("igs_common.digest")

PROMPT_VERSION = "digest-summary-v1"

INSTRUCTIONS = """\
Sos el jefe de operaciones de Infinity Global Sports (giras deportivas). Escribí la apertura del
resumen de la mañana para el equipo de ops, en español rioplatense, directo y sin saludo.

Reglas:
- 2 o 3 oraciones, máximo 60 palabras. Empezá por lo más urgente (el riesgo con rank 1).
- Usá SOLO datos del JSON. No inventes montos, fechas, cantidades ni nombres.
- Todo número que escribas tiene que estar en el JSON, escrito con dígitos. Si dudás, no lo pongas.
- No repitas la lista completa: el detalle va debajo. Decí qué hacer primero.
- Nada de horas del día, porcentajes ni estimaciones.
"""


class SummaryOut(BaseModel):
    summary: str = Field(max_length=600)


@dataclass(frozen=True)
class Phrased:
    summary: str
    source: Literal["llm", "template"]
    model: str | None = None
    rejected: tuple[str, ...] = ()  # numbers the model wrote that the facts don't support


def template_summary(facts: DigestFacts) -> str:
    c = facts.counts
    parts = []
    if facts.risks:
        top = facts.risks[0]
        parts.append(f"Lo primero: {top.name} — {top.next_action.rstrip('. ')}.")
    tally = [
        _n(c.red_accounts, "cliente en rojo", "clientes en rojo"),
        _n(c.payments_overdue, "pago vencido", "pagos vencidos"),
        _n(c.approvals_pending, "aprobación esperando", "aprobaciones esperando"),
        _n(
            c.departures,
            f"salida en {facts.rules.departure_window_days} días",
            f"salidas en {facts.rules.departure_window_days} días",
        ),
        _n(c.stale_leads, "lead sin respuesta", "leads sin respuesta"),
    ]
    tally = [t for t in tally if t]
    if tally:
        parts.append("Hoy: " + _join(tally) + ".")
    return " ".join(parts) or "Sin pendientes urgentes hoy."


async def phrase_summary(
    llm: LLMClient | None, facts: DigestFacts, *, role: Role = Role.FAST
) -> Phrased:
    fallback = template_summary(facts)
    if llm is None:
        return Phrased(fallback, "template")
    payload = facts.to_json()
    allowed = allowed_numbers(payload)
    items: list[Message] = [
        Message("user", "Datos del día (JSON):\n" + json.dumps(payload, ensure_ascii=False))
    ]
    rejected: tuple[str, ...] = ()
    for _attempt in range(2):
        try:
            result = await llm.generate(
                role,
                items,
                output_model=SummaryOut,
                options=GenerateOptions(
                    instructions=INSTRUCTIONS,
                    max_output_tokens=400,
                    reasoning_effort="low",
                    metadata={"prompt": PROMPT_VERSION},
                ),
            )
        except LLMError:
            log.warning("digest_summary_llm_failed", exc_info=True)
            return Phrased(fallback, "template", rejected=rejected)
        text = (result.parsed.summary if result.parsed else result.text).strip()
        check = check_numbers(text, allowed)
        if text and check.ok:
            return Phrased(text, "llm", model=result.model)
        rejected = check.unknown
        log.info("digest_summary_rejected", unknown=list(check.unknown))
        items = [
            *items,
            Message("assistant", text),
            Message(
                "user",
                "Estos números no están en los datos: "
                + ", ".join(check.unknown or ("(texto vacío)",))
                + ". Reescribí sin ellos.",
            ),
        ]
    return Phrased(fallback, "template", rejected=rejected)


def _n(count: int, one: str, many: str) -> str | None:
    if count == 0:
        return None
    return f"{count} {one if count == 1 else many}"


def _join(parts: list[str]) -> str:
    return parts[0] if len(parts) == 1 else ", ".join(parts[:-1]) + " y " + parts[-1]
