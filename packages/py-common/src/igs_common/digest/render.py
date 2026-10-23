"""Digest → email HTML (inline CSS, the site's dark style), plain text and JSON.

Email clients ignore <style> blocks and web fonts unevenly, so everything is inline and
table-based, with system fallbacks after the site fonts. No IGS logo or photos: the mark is
the text "IGS OS". All dynamic text is escaped.
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from html import escape
from typing import Any

from igs_common.money import usd_es

from .phrase import Phrased
from .types import DigestFacts, Payment

# docs/design/igs-site-style.md
BG, CARD, RAISED = "#0D0D0D", "#171717", "#262626"
FG, MUTED, MUTED_HEAD = "#F2F2F2", "#999999", "#7A7A7A"
LINE = "#2A2A2A"  # white/10 on #0D0D0D, flattened for clients without rgba
RED, AMBER, GREEN = "#F87171", "#FBBF24", "#4ADE80"
CONDENSED = "'Barlow Condensed','Arial Narrow',Arial,sans-serif"
SANS = "'DM Sans',Helvetica,Arial,sans-serif"
BODY = "Montserrat,Helvetica,Arial,sans-serif"

_WEEKDAYS = ("lunes", "martes", "miércoles", "jueves", "viernes", "sábado", "domingo")
_MONTHS = (
    "enero", "febrero", "marzo", "abril", "mayo", "junio", "julio", "agosto", "septiembre",
    "octubre", "noviembre", "diciembre",
)  # fmt: skip


def render_json(facts: DigestFacts, phrased: Phrased) -> dict[str, Any]:
    return {
        "summary": phrased.summary,
        "summary_source": phrased.source,
        "summary_model": phrased.model,
        "facts": facts.to_json(),
    }


# ── Plain text ─────────────────────────────────────────────────────────────


def render_text(facts: DigestFacts, phrased: Phrased, *, base_url: str = "") -> str:
    c = facts.counts
    lines = [
        f"IGS OS · Resumen de operación · {long_date(facts.day)}",
        "",
        phrased.summary,
        "",
        f"Clientes en rojo {c.red_accounts} · Pagos {c.payments_due} · "
        f"Aprobaciones {c.approvals_pending} · Salidas {c.departures} · "
        f"Leads sin respuesta {c.stale_leads}",
    ]

    def section(title: str, rows: list[str]) -> None:
        lines.extend(["", title.upper(), *(rows or ["  Nada pendiente."])])

    section(
        "Riesgos",
        [
            f"  {r.rank}. {r.name} [{_level(r.level)}] — {r.reason}\n"
            f"     → {r.next_action}\n     {base_url}{r.link}"
            for r in facts.risks
        ],
    )
    section(
        "Pagos",
        [f"  · {p.name}: {payment_line(p)}\n     {base_url}{p.link}" for p in facts.payments],
    )
    section(
        f"Aprobaciones ({c.approvals_pending})",
        [
            f"  · {a.title} — espera hace {hours(a.waiting_hours)}"
            + (f", vence en {hours(a.expires_in_hours)}" if a.expires_in_hours is not None else "")
            + f"\n     {base_url}{a.link}"
            for a in facts.approvals
        ],
    )
    section(
        f"Salidas en {facts.rules.departure_window_days} días",
        [
            f"  · {d.code or d.title} {d.account_name or ''} — sale en {d.days_to_departure} días"
            f" ({short_date(d.start_date)}), {d.open_items} ítems sin confirmar\n"
            f"     {base_url}{d.link}"
            for d in facts.departures
        ],
    )
    section(
        f"Leads sin respuesta (> {facts.rules.lead_sla_business_days} día hábil)",
        [
            f"  · {s.organization} ({s.sport}, {s.group_size} personas) — "
            f"{s.business_days_waiting} días hábiles esperando\n     {base_url}{s.link}"
            for s in facts.stale_leads
        ],
    )
    lines.extend(["", _footer_text(phrased)])
    return "\n".join(lines) + "\n"


# ── HTML email ─────────────────────────────────────────────────────────────


def render_html(facts: DigestFacts, phrased: Phrased, *, base_url: str = "") -> str:
    c = facts.counts
    e = escape
    kpis = [
        ("En rojo", c.red_accounts),
        ("Pagos", c.payments_due),
        ("Aprobaciones", c.approvals_pending),
        ("Salidas", c.departures),
        ("Leads", c.stale_leads),
    ]
    kpi_cells = "".join(
        f'<td style="padding:16px 8px 16px 0;vertical-align:top;width:20%">'
        f'<div style="font-family:{CONDENSED};font-weight:900;font-size:44px;line-height:.85;'
        f'color:{FG}">{n}</div>'
        f'<div style="font-family:{BODY};font-weight:600;font-size:11px;letter-spacing:.06em;'
        f'text-transform:uppercase;color:{MUTED};padding-top:6px">{e(label)}</div></td>'
        for label, n in kpis
    )

    risks = "".join(
        _card(
            eyebrow=f"{r.rank} · {_level(r.level)}",
            eyebrow_color=_level_color(r.level),
            title=r.name,
            body=r.reason,
            action=r.next_action,
            href=base_url + r.link,
        )
        for r in facts.risks
    )
    payments = "".join(
        _row(p.name, payment_line(p), base_url + p.link, RED if p.overdue else None)
        for p in facts.payments
    )
    approvals = "".join(
        _row(
            a.title,
            f"Espera hace {hours(a.waiting_hours)}"
            + (
                f" · vence en {hours(a.expires_in_hours)}" if a.expires_in_hours is not None else ""
            ),
            base_url + a.link,
        )
        for a in facts.approvals
    )
    departures = "".join(
        _row(
            f"{d.code or ''} {d.account_name or d.title}".strip(),
            f"Sale en {d.days_to_departure} días ({short_date(d.start_date)}) · "
            f"{d.open_items} ítems sin confirmar",
            base_url + d.link,
            AMBER if d.open_items else None,
        )
        for d in facts.departures
    )
    leads = "".join(
        _row(
            s.organization,
            f"{s.sport} · {s.group_size} personas · "
            f"{s.business_days_waiting} días hábiles esperando",
            base_url + s.link,
            RED,
        )
        for s in facts.stale_leads
    )

    sections = [
        _section("Riesgos", c.risks, risks),
        _section("Pagos", c.payments_due, payments),
        _section("Aprobaciones", c.approvals_pending, approvals),
        _section(f"Salidas en {facts.rules.departure_window_days} días", c.departures, departures),
        _section("Leads sin respuesta", c.stale_leads, leads),
    ]

    table = 'role="presentation" width="100%" cellpadding="0" cellspacing="0"'
    pill = (
        f"display:inline-block;font-family:{BODY};font-weight:600;font-size:12px;"
        "color:#171717;background:#FFFFFF;border-radius:9999px;padding:7px 16px"
    )
    eyebrow = (
        f"font-family:{SANS};font-weight:600;font-size:13px;letter-spacing:.375em;"
        f"text-transform:uppercase;color:{FG};padding-bottom:14px"
    )
    mega = (
        f"font-family:{CONDENSED};font-weight:900;font-size:64px;line-height:.8;"
        "letter-spacing:-.025em;text-transform:uppercase;padding-bottom:22px"
    )
    lead = f"font-family:{BODY};font-size:17px;line-height:27px;color:{FG};padding-bottom:8px"
    footer = f"padding-top:32px;font-family:{BODY};font-size:12px;line-height:18px;color:{MUTED}"
    marquee = (
        f"padding-top:20px;font-family:{CONDENSED};font-weight:800;font-size:18px;"
        f"letter-spacing:.2em;text-transform:uppercase;color:{RAISED}"
    )
    day = e(long_date(facts.day))
    return f"""<!doctype html>
<html lang="es"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<meta name="color-scheme" content="dark"><meta name="supported-color-schemes" content="dark">
<title>Resumen de operación · {day}</title></head>
<body style="margin:0;padding:0;background:{BG};color:{FG}">
<div style="display:none;max-height:0;overflow:hidden">{e(phrased.summary)}</div>
<table {table} style="background:{BG}">
<tr><td align="center" style="padding:24px 16px">
<table {table} style="max-width:640px">
<tr><td style="padding-bottom:28px"><span style="{pill}">IGS OS</span></td></tr>
<tr><td style="{eyebrow}">{day}</td></tr>
<tr><td style="{mega}">
<span style="color:{MUTED_HEAD}">Hoy en</span><br>
<span style="color:{FG}">operación.</span></td></tr>
<tr><td style="{lead}">{e(phrased.summary)}</td></tr>
<tr><td style="border-bottom:1px solid {LINE}">
<table {table}><tr>{kpi_cells}</tr></table></td></tr>
{"".join(sections)}
<tr><td style="{footer}">{e(_footer_text(phrased))}</td></tr>
<tr><td style="{marquee}">Train. Compete. Experience.</td></tr>
</table></td></tr></table></body></html>
"""


def _section(title: str, count: int, rows: str) -> str:
    empty = (
        f'<div style="font-family:{BODY};font-size:14px;color:{MUTED};padding:12px 0">'
        "Nada pendiente.</div>"
    )
    return (
        f'<tr><td style="padding-top:36px">'
        f'<div style="font-family:{SANS};font-size:32px;line-height:.9;letter-spacing:-.06em;'
        f'color:{FG};padding-bottom:14px">{escape(title)} '
        f'<span style="color:{MUTED_HEAD}">{count}</span></div>{rows or empty}</td></tr>'
    )


def _card(
    *, eyebrow: str, eyebrow_color: str, title: str, body: str, action: str, href: str
) -> str:
    e = escape
    return (
        f'<table role="presentation" width="100%" cellpadding="0" cellspacing="0" '
        f'style="background:{CARD};border:1px solid {LINE};border-radius:8px;margin-bottom:10px">'
        f'<tr><td style="padding:18px 20px">'
        f'<div style="font-family:{BODY};font-weight:600;font-size:11px;letter-spacing:.08em;'
        f'text-transform:uppercase;color:{eyebrow_color};padding-bottom:8px">{e(eyebrow)}</div>'
        f'<div style="font-family:{SANS};font-size:24px;line-height:1;letter-spacing:-.05em;'
        f'color:{FG};padding-bottom:8px">{e(title)}</div>'
        f'<div style="font-family:{BODY};font-size:14px;line-height:21px;color:{MUTED};'
        f'padding-bottom:12px">{e(body)}</div>'
        f'<div style="font-family:{BODY};font-size:14px;line-height:21px;color:{FG};'
        f'padding-bottom:14px">→ {e(action)}</div>'
        f'<a href="{e(href, quote=True)}" style="display:inline-block;font-family:{BODY};'
        f"font-weight:600;font-size:12px;color:#171717;background:#FFFFFF;border-radius:9999px;"
        f'padding:8px 16px;text-decoration:none">Abrir →</a></td></tr></table>'
    )


def _row(title: str, detail: str, href: str, accent: str | None = None) -> str:
    e = escape
    bar = accent or LINE
    return (
        f'<table role="presentation" width="100%" cellpadding="0" cellspacing="0" '
        f'style="border-bottom:1px solid {LINE}"><tr>'
        f'<td style="width:3px;background:{bar}"></td>'
        f'<td style="padding:12px 14px">'
        f'<a href="{e(href, quote=True)}" style="font-family:{SANS};font-size:17px;'
        f'letter-spacing:-.03em;color:{FG};text-decoration:none">{e(title)}</a>'
        f'<div style="font-family:{BODY};font-size:13px;line-height:19px;color:{MUTED};'
        f'padding-top:3px">{e(detail)}</div></td>'
        f'<td style="padding:12px 0;text-align:right;white-space:nowrap">'
        f'<a href="{e(href, quote=True)}" style="font-family:{BODY};font-weight:600;font-size:12px;'
        f'color:{MUTED};text-decoration:none">Abrir →</a></td></tr></table>'
    )


# ── Shared formatting ──────────────────────────────────────────────────────


def payment_line(p: Payment) -> str:
    amount = f"{usd(p.amount_usd)} · " if p.amount_usd is not None else ""
    if p.days < 0:
        when = f"vencido hace {-p.days} {'día' if p.days == -1 else 'días'}"
    elif p.days == 0:
        when = "vence hoy"
    else:
        when = f"vence en {p.days} {'día' if p.days == 1 else 'días'}"
    return f"{p.label} — {amount}{when} ({short_date(p.due_date)})"


def usd(amount: Decimal) -> str:
    return usd_es(amount)


def hours(h: int) -> str:
    if h < 48:
        return f"{h} h"
    return f"{h // 24} días"


def long_date(d: date) -> str:
    return f"{_WEEKDAYS[d.weekday()]} {d.day} de {_MONTHS[d.month - 1]}"


def short_date(d: date) -> str:
    return f"{d:%d/%m}"


def _level(level: str) -> str:
    return {
        "red": "rojo",
        "amber": "ámbar",
        "critical": "crítico",
        "high": "alto",
        "medium": "medio",
    }.get(level, level)


def _level_color(level: str) -> str:
    return RED if level in ("red", "critical", "high") else AMBER


def _footer_text(phrased: Phrased) -> str:
    source = (
        "La apertura la redactó un modelo y se verificó: cada número está en los datos."
        if phrased.source == "llm"
        else "Apertura generada por reglas."
    )
    return f"Generado por IGS OS con los mismos datos que la pantalla Hoy. {source}"
