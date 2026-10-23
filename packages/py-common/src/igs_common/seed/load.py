"""Idempotent demo seed: upserts the YAML fixtures in `packages/py-common/fixtures/`.

    async with system_scope() as session:
        report = await load(session)

Every row gets a deterministic UUID derived from (tenant slug, kind, fixture key), so running the
seed again updates rows in place instead of duplicating them — and never truncates, so leads, trips
or executions created while demoing survive a re-seed. Seeded ids are UUIDv5, not the v7 the app
generates; they only need to be stable.

Fixture fields with no dedicated column (the team snapshot, active flow) ride along in the
trip's `pricing` snapshot.
"""

import hashlib
import json
import uuid
from collections.abc import Iterable, Mapping
from dataclasses import dataclass, field
from datetime import UTC, date, datetime, timedelta
from datetime import time as dt_time
from pathlib import Path
from typing import Any

import yaml
from sqlalchemy import text
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from igs_common.db.models import (
    Account,
    AccountFact,
    Approval,
    AuditLog,
    Contact,
    Document,
    Experience,
    Flow,
    FlowExecution,
    FlowNodeRun,
    FlowTrigger,
    FlowVersion,
    Interaction,
    Lead,
    Opponent,
    Provider,
    Stakeholder,
    Tenant,
    Traveler,
    TravelerDocument,
    Trip,
    TripItem,
    User,
)
from igs_common.db.rls import TENANT_GUC
from igs_common.domain.approvals import canonical_json, payload_hash
from igs_common.seed.anchor import shift_days, shift_tree

_PACKAGE_ROOT = Path(__file__).resolve().parents[3]
FIXTURES_DIR = _PACKAGE_ROOT / "fixtures"
FLOW_EXAMPLES_DIR = _PACKAGE_ROOT.parent / "flow-schema" / "examples"

# Fixed namespace for fixture ids. Changing it re-keys every seeded row.
_NAMESPACE = uuid.UUID("5b0f3c1e-6a43-4c2b-9d0e-1a2b3c4d5e6f")

# The fixtures' "now". Seeding replays them relative to today (see seed/anchor.py): every date in
# sales/accounts — structured or written in text — moves by `anchor - FIXTURE_ANCHOR` days.
DEMO_NOW = datetime.fromisoformat("2026-10-22T10:15:00-03:00")

_FLOW_PUBLISHED_AT = datetime.fromisoformat("2026-10-01T09:00:00-03:00")


@dataclass
class SeedReport:
    tenant_id: uuid.UUID | None = None
    counts: dict[str, int] = field(default_factory=dict)
    warnings: list[str] = field(default_factory=list)


def fixture_id(tenant_slug: str, kind: str, key: str) -> uuid.UUID:
    return uuid.uuid5(_NAMESPACE, f"{tenant_slug}/{kind}/{key}")


async def load(
    session: AsyncSession,
    *,
    fixtures_dir: Path | None = None,
    flows_dir: Path | None = None,
    tenant_slug: str = "igs",
) -> SeedReport:
    """Upsert the demo tenant and all its fixtures inside the caller's transaction.

    Dates are anchored to ``DEMO_ANCHOR`` (default: today in Buenos Aires), so every reset tells
    the same story relative to the day it runs.
    """
    days = shift_days()
    fx = _Fixtures(fixtures_dir or FIXTURES_DIR, flows_dir or FLOW_EXAMPLES_DIR, days=days)
    seeder = _Seeder(session, tenant_slug, days=days)
    await seeder.run(fx)
    return seeder.report


# ── Fixture files ──────────────────────────────────────────────────────────


class _Fixtures:
    def __init__(self, root: Path, flows_dir: Path, *, days: int = 0) -> None:
        self.tenant = shift_tree(_read(root / "tenant.yaml"), days)
        # The catalog is timeless (seasons, policies); only the story moves with the anchor.
        self.catalog = _read(root / "catalog.yaml")
        self.sales = shift_tree(_read(root / "sales.yaml"), days)
        self.accounts = shift_tree(_read(root / "accounts.yaml"), days)["accounts"]
        roster = root / "travelers.yaml"
        self.travelers: list[dict[str, Any]] = (
            shift_tree(_read(roster), days, texts=False)["travelers"] if roster.is_file() else []
        )
        self.flows_dir = flows_dir
        self.flows = (
            [json.loads(p.read_text(encoding="utf-8")) for p in sorted(flows_dir.glob("*.json"))]
            if flows_dir.is_dir()
            else None
        )


def _read(path: Path) -> dict[str, Any]:
    with path.open(encoding="utf-8") as f:
        data = yaml.safe_load(f)
    if not isinstance(data, dict):
        raise ValueError(f"{path} must contain a mapping")
    return data


# ── Seeder ─────────────────────────────────────────────────────────────────


class _Seeder:
    def __init__(self, session: AsyncSession, tenant_slug: str, *, days: int = 0) -> None:
        self.session = session
        self.slug = tenant_slug
        self.now = DEMO_NOW + timedelta(days=days)
        self.flow_published_at = _FLOW_PUBLISHED_AT + timedelta(days=days)
        self.report = SeedReport()
        self.tenant_id: uuid.UUID | None = None

    def id(self, kind: str, key: str) -> uuid.UUID:
        return fixture_id(self.slug, kind, key)

    def ref(self, kind: str, key: str | None) -> uuid.UUID | None:
        return self.id(kind, key) if key else None

    def warn(self, message: str) -> None:
        if message not in self.report.warnings:
            self.report.warnings.append(message)

    async def run(self, fx: _Fixtures) -> None:
        await self.tenant(fx.tenant)
        await self.users(fx.tenant.get("users", []))
        await self.catalog(fx.catalog)
        await self.accounts(fx.accounts)
        contacts_by_email = await self.contacts(fx.sales["contacts"])
        await self.leads(fx.sales["leads"])
        await self.trips(fx.sales["trips"], fx.catalog)
        await self.travelers(fx.travelers)
        await self.account_details(fx.accounts, contacts_by_email)
        if fx.flows is not None:
            await self.flows(fx.flows)
            await self.flow_triggers(fx.flows)
            await self.executions(fx.sales.get("executions", []))
        else:
            self.warn(f"flow examples not found at {fx.flows_dir}; skipped flows")
        await self.approvals(fx.sales["approvals"])
        await self.activity(fx.sales.get("activity", []))

    # tenancy

    async def tenant(self, data: Mapping[str, Any]) -> None:
        t = data["tenant"]
        stmt = pg_insert(Tenant).values(
            id=fixture_id(self.slug, "tenant", self.slug),
            slug=self.slug,
            name=t["name"],
            settings=t.get("settings", {}),
        )
        stmt = stmt.on_conflict_do_update(
            index_elements=[Tenant.slug],
            set_={"name": stmt.excluded.name, "settings": stmt.excluded.settings},
        ).returning(Tenant.id)
        self.tenant_id = (await self.session.execute(stmt)).scalar_one()
        self.report.tenant_id = self.tenant_id
        self.report.counts["tenants"] = 1
        # Lets the seed run under the app role too: RLS policies read this GUC.
        await self.session.execute(
            text("SELECT set_config(:guc, :tid, true)"),
            {"guc": TENANT_GUC, "tid": str(self.tenant_id)},
        )

    async def users(self, users: list[dict[str, Any]]) -> None:
        await self.upsert(
            User,
            [
                {
                    "id": self.id("user", u["key"]),
                    "email": u["email"],
                    "name": u["name"],
                    "role": u["role"],
                }
                for u in users
            ],
        )

    # catalog

    async def catalog(self, cat: Mapping[str, Any]) -> None:
        await self.upsert(
            Provider,
            [
                {
                    "id": self.id("provider", p["key"]),
                    "name": p["name"],
                    "kind": p["kind"],
                    "city": p["city"],
                    "country": p["country"],
                    "contact": p["contact"],
                    "unit_price_usd": p["unit_price_usd"],
                    "unit": p["unit"],
                }
                for p in cat["providers"]
            ],
        )
        await self.upsert(
            Opponent,
            [
                {
                    "id": self.id("opponent", o["key"]),
                    "name": o["name"],
                    "city": o["city"],
                    "country": o["country"],
                    "sport": o["sport"],
                    "gender": o["gender"],
                    "age_groups": o["age_groups"],
                    "level_score": o["level_score"],
                    "description": o["description"],
                    "provider_id": self.ref("provider", o.get("provider")),
                }
                for o in cat["opponents"]
            ],
        )
        await self.upsert(
            Experience,
            [
                {
                    "id": self.id("experience", e["key"]),
                    "title": e["title"],
                    "city": e["city"],
                    "country": e["country"],
                    "sports": e["sports"],
                    "duration_hours": e["duration_hours"],
                    "price_usd": e["price_usd"],
                    "description": e["description"],
                    "provider_id": self.ref("provider", e.get("provider")),
                }
                for e in cat["experiences"]
            ],
        )
        # Knowledge documents land as `pending`; the ingestion workflow chunks and indexes them
        # from `inline_content` (small seeded sources never go through GCS).
        await self.upsert(
            Document,
            [
                {
                    "id": self.id("document", d["key"]),
                    "title": d["title"],
                    "source": d["source"],
                    "mime_type": d.get("mime_type", "text/markdown"),
                    "content_hash": _sha256(d["content"]),
                    "inline_content": d["content"],
                    "metadata": {"fixture_key": d["key"]},
                    "status": "pending",
                }
                for d in cat["documents"]
            ],
        )

    # sales and operations

    async def accounts(self, accounts: list[dict[str, Any]]) -> None:
        await self.upsert(
            Account,
            [
                {
                    "id": self.id("account", a["key"]),
                    "name": a["name"],
                    "kind": a["kind"],
                    "country": a["country"],
                    "state": a.get("state"),
                    "city": a.get("city"),
                    "sport_programs": a.get("sport_programs", []),
                    "tier": a.get("tier"),
                    "owner_user_id": self.ref("user", a.get("owner")),
                    "status": a["status"],
                    "health": a["health"],
                }
                for a in accounts
            ],
        )

    async def contacts(self, contacts: list[dict[str, Any]]) -> dict[str, uuid.UUID]:
        rows = [
            {
                "id": self.id("contact", c["key"]),
                "name": c["name"],
                "email": c.get("email"),
                "phone": c.get("phone"),
                "organization": c.get("organization"),
                "role": c.get("role"),
                "account_id": self.ref("account", c.get("account")),
            }
            for c in contacts
        ]
        await self.upsert(Contact, rows)
        return {r["email"].lower(): r["id"] for r in rows if r["email"]}

    async def leads(self, leads: list[dict[str, Any]]) -> None:
        rows = []
        for lead in leads:
            goals = "\n".join(
                part
                for part in (
                    f"{lead['organization']} · {lead['program']} · {lead['travel_window']}",
                    lead.get("agent_summary"),
                    f"Next step: {lead['next_step']}" if lead.get("next_step") else None,
                )
                if part
            )
            rows.append(
                {
                    "id": self.id("lead", lead["key"]),
                    "contact_id": self.ref("contact", lead.get("contact")),
                    "account_id": self.ref("account", lead.get("account")),
                    "sport": lead["sport"],
                    "gender": lead["gender"],
                    "age_group": lead["age_group"],
                    "level_score": lead["level_score"],
                    "group_size": lead["group_size"],
                    "destination_country": lead["destination_country"],
                    "travel_start": _date(lead["travel_start"]),
                    "duration_days": lead["duration_days"],
                    "budget_per_person_usd": lead.get("budget_per_person_usd"),
                    "goals": goals,
                    "status": lead["status"],
                    "source": lead["source"],
                    "lost_reason": lead.get("lost_reason"),
                    "updated_at": _dt(lead.get("last_activity_at")),
                }
            )
        await self.upsert(Lead, rows)

    async def trips(self, trips: list[dict[str, Any]], cat: Mapping[str, Any]) -> None:
        opponents = {o["key"] for o in cat["opponents"]}
        experiences = {e["key"] for e in cat["experiences"]}
        trip_rows, item_rows = [], []
        for t in trips:
            team = t["team"]
            total = t["price_per_person_usd"] * t["travelers"]
            trip_rows.append(
                {
                    "id": self.id("trip", t["key"]),
                    "lead_id": self.ref("lead", t.get("lead")),
                    "account_id": self.ref("account", t.get("account")),
                    "code": t["code"],
                    "title": t["title"],
                    "city": t["city"],
                    "country": t["country"],
                    "start_date": _date(t["start_date"]),
                    "end_date": _date(t["end_date"]),
                    "status": t["status"],
                    "price_per_person_usd": t["price_per_person_usd"],
                    "travelers": t["travelers"],
                    "owner_user_id": self.ref("user", t.get("owner")),
                    "summary": (
                        f"{team['name']} {team['program']} (level {team['level_score']}), "
                        f"{t['travelers']} travelers, {t['city']} "
                        f"{t['start_date']} → {t['end_date']}."
                    ),
                    # Quote snapshot, plus the team profile and active flow for the panel.
                    "pricing": {
                        "currency": "USD",
                        "price_per_person_usd": t["price_per_person_usd"],
                        "total_usd": total,
                        "deposit_paid_pct": t.get("deposit_paid_pct", 0),
                        "paid_usd": round(total * t.get("deposit_paid_pct", 0) / 100),
                        **({"payment_terms": t["payment_terms"]} if t.get("payment_terms") else {}),
                        "active_flow": t.get("active_flow"),
                        "team": team,
                    },
                }
            )
            for item in t["items"]:
                opponent = item.get("opponent")
                experience = item.get("experience")
                notes = [n for n in (item.get("detail"), item.get("notes")) if n]
                if item.get("opponent_name"):
                    name, level = item["opponent_name"], item["opponent_level"]
                    notes.append(f"Opponent: {name} (level {level})")
                item_rows.append(
                    {
                        "id": self.id("trip_item", item["key"]),
                        "trip_id": self.id("trip", t["key"]),
                        "day": item["day"],
                        "slot": item["slot"],
                        "kind": item["kind"],
                        "title": item["title"],
                        "opponent_id": self.id("opponent", opponent)
                        if opponent in opponents
                        else None,
                        "experience_id": (
                            self.id("experience", experience) if experience in experiences else None
                        ),
                        "provider_id": self.ref("provider", item.get("provider")),
                        "status": item["status"],
                        "notes": " · ".join(notes) or None,
                        "time": _time(item.get("time")),
                        "alert": item.get("alert"),
                        "requested_at": _requested_at(item, self.now),
                    }
                )
        await self.upsert(Trip, trip_rows)
        await self.upsert(TripItem, item_rows)

    async def travelers(self, travelers: list[dict[str, Any]]) -> None:
        """The roster and each traveler's pre-departure document status (never the documents)."""
        people, docs = [], []
        for t in travelers:
            traveler_id = self.id("traveler", t["key"])
            people.append(
                {
                    "id": traveler_id,
                    "trip_id": self.id("trip", t["trip"]),
                    "full_name": t["full_name"],
                    "role": t["role"],
                    "is_minor": t.get("is_minor", False),
                    "birth_year": t.get("birth_year"),
                }
            )
            for requirement, value in (t.get("documents") or {}).items():
                doc = value if isinstance(value, dict) else {"status": value}
                docs.append(
                    {
                        "id": self.id("traveler_document", f"{t['key']}:{requirement}"),
                        "traveler_id": traveler_id,
                        "requirement": requirement,
                        "status": doc["status"],
                        "valid_from": _opt_date(doc.get("valid_from")),
                        "valid_until": _opt_date(doc.get("valid_until")),
                        "note": doc.get("note"),
                    }
                )
        await self.upsert(Traveler, people)
        await self.upsert(TravelerDocument, docs)

    async def account_details(
        self, accounts: list[dict[str, Any]], contacts_by_email: Mapping[str, uuid.UUID]
    ) -> None:
        stakeholders, interactions, facts = [], [], []
        for a in accounts:
            account_id = self.id("account", a["key"])
            last_contact: dict[str, datetime] = {}
            for i in a["interactions"]:
                occurred = _dt(i["occurred_at"])
                assert occurred is not None
                if i.get("stakeholder"):
                    prev = last_contact.get(i["stakeholder"])
                    last_contact[i["stakeholder"]] = max(prev, occurred) if prev else occurred
                interactions.append(
                    {
                        "id": self.id("interaction", i["key"]),
                        "account_id": account_id,
                        "stakeholder_id": self.ref("stakeholder", i.get("stakeholder")),
                        "channel": i["channel"],
                        "direction": i["direction"],
                        "occurred_at": occurred,
                        "subject": i.get("subject"),
                        "body": i["body"].strip(),
                        "trip_id": self.ref("trip", i.get("trip")),
                        "lead_id": self.ref("lead", i.get("lead")),
                    }
                )
            for s in a["stakeholders"]:
                email = (s.get("email") or "").lower()
                stakeholders.append(
                    {
                        "id": self.id("stakeholder", s["key"]),
                        "account_id": account_id,
                        "contact_id": contacts_by_email.get(email),
                        "name": s["name"],
                        "title": s.get("title"),
                        "role": s["role"],
                        "influence": s.get("influence"),
                        "sentiment": s.get("sentiment"),
                        "email": s.get("email"),
                        "phone": s.get("phone"),
                        "preferred_channel": s.get("preferred_channel"),
                        "last_contact_at": last_contact.get(s["key"]),
                        "notes": s.get("notes"),
                    }
                )
            for f in a["facts"]:
                facts.append(
                    {
                        "id": self.id("account_fact", f["key"]),
                        "account_id": account_id,
                        "kind": f["kind"],
                        "statement": f["statement"],
                        "confidence": f["confidence"],
                        "source_interaction_id": self.id("interaction", f["source"]),
                        "valid_from": _dt(f["valid_from"]),
                        "severity": f.get("severity"),
                        "due_date": _date(f["due_date"]) if f.get("due_date") else None,
                        "status": f.get("status", "open"),
                    }
                )
        await self.upsert(Stakeholder, stakeholders)
        await self.upsert(Interaction, interactions)
        await self.upsert(AccountFact, facts)

    # flows

    async def flows(self, graphs: list[dict[str, Any]]) -> None:
        flows, versions = [], []
        for graph in graphs:
            key = graph["id"]
            flow_id, version_id = self.id("flow", key), self.id("flow_version", f"{key}@1")
            flows.append(
                {
                    "id": flow_id,
                    "key": key,
                    "name": graph["name"],
                    "description": graph.get("description"),
                    "draft_graph": graph,
                }
            )
            versions.append(
                {
                    "id": version_id,
                    "flow_id": flow_id,
                    "version": 1,
                    "graph": graph,
                    "graph_hash": _sha256(canonical_json(graph)),
                    "schema_version": str(graph.get("schemaVersion", "1")),
                    "published_by": self.id("user", "martin.rios"),
                    "published_at": self.flow_published_at,
                    "changelog": "Initial version (seed)",
                }
            )
        await self.upsert(Flow, flows)
        await self.upsert(FlowVersion, versions)
        # Second pass once the versions exist (flows ↔ flow_versions reference each other).
        await self.upsert(
            Flow,
            [
                {**f, "published_version_id": self.id("flow_version", f"{f['key']}@1")}
                for f in flows
            ],
            count=False,
        )

    async def flow_triggers(self, graphs: list[dict[str, Any]]) -> None:
        # What publishing derives from the graph; the outbox dispatcher matches against these.
        rows = []
        for graph in graphs:
            trigger = dict(graph["trigger"])
            kind = trigger.pop("type")
            rows.append(
                {
                    "id": self.id("flow_trigger", graph["id"]),
                    "flow_id": self.id("flow", graph["id"]),
                    "kind": kind,
                    "config": trigger,
                    "enabled": True,
                }
            )
        await self.upsert(FlowTrigger, rows)

    async def executions(self, executions: list[dict[str, Any]]) -> None:
        """Executions frozen mid-flight for the demo (e.g. waiting on an ops approval).

        Shapes follow what the worker records: one node run per visited node, `waiting` on the
        node the execution is parked at. There is no live Temporal workflow behind them, so a
        decision on their approval is recorded but its signal is not delivered.
        """
        exec_rows, run_rows = [], []
        for e in executions:
            execution_id = self.id("execution", e["key"])
            subject_kind, subject_key = next(iter(e["subject"].items()))
            exec_rows.append(
                {
                    "id": execution_id,
                    "flow_version_id": self.id("flow_version", f"{e['flow']}@1"),
                    "trigger_kind": e["trigger_kind"],
                    "trigger_payload": self.resolve(e.get("trigger_payload", {})),
                    "status": e["status"],
                    "temporal_workflow_id": f"seed-{self.slug}-{e['key']}",
                    "vars": self.resolve(e.get("vars", {})),
                    "started_at": _dt(e["started_at"]),
                    "finished_at": _dt(e.get("finished_at")),
                    "subject_type": subject_kind,
                    "subject_id": self.id(subject_kind, subject_key),
                }
            )
            for n, run in enumerate(e["node_runs"]):
                started, finished = _dt(run["started_at"]), _dt(run.get("finished_at"))
                assert started is not None
                run_rows.append(
                    {
                        "id": self.id("node_run", f"{e['key']}/{n}"),
                        "execution_id": execution_id,
                        "node_id": run["node"],
                        "node_type": run["type"],
                        "attempt": 1,
                        "status": run["status"],
                        "input": self.resolve(run.get("input")),
                        "output": self.resolve(run.get("output")),
                        "started_at": started,
                        "finished_at": finished,
                        "duration_ms": (
                            int((finished - started).total_seconds() * 1000) if finished else None
                        ),
                        "idempotency_key": f"{execution_id}:{run['node']}:1",
                    }
                )
        await self.upsert(FlowExecution, exec_rows)
        await self.upsert(FlowNodeRun, run_rows)

    def resolve(self, value: Any) -> Any:
        """Fixture references like "@trip:t-2711" become the seeded row's UUID (as a string)."""
        if isinstance(value, str) and value.startswith("@") and ":" in value:
            kind, key = value[1:].split(":", 1)
            return str(self.id(kind, key))
        if isinstance(value, dict):
            return {k: self.resolve(v) for k, v in value.items()}
        if isinstance(value, list):
            return [self.resolve(v) for v in value]
        return value

    async def approvals(self, approvals: list[dict[str, Any]]) -> None:
        rows = []
        for a in approvals:
            action, params = _proposed_action(a)
            params = self.resolve(params)
            subject_kind = "trip" if a.get("trip") else "lead"
            subject_key = a.get(subject_kind)
            subject_id = self.id(subject_kind, subject_key) if subject_key else None
            details = {
                **a["details"],
                "flow": a.get("flow"),
                "flow_label": a.get("flow_label"),
                "node_label": a.get("node"),
                "requested_by": a.get("requested_by"),
            }
            rows.append(
                {
                    "id": self.id("approval", a["key"]),
                    "execution_id": self.ref("execution", a.get("execution")),
                    "node_id": a.get("node_id"),
                    "subject_type": subject_kind if subject_id else None,
                    "subject_id": subject_id,
                    "title": a["title"],
                    "details": details,
                    "proposed_action": {"action": action, "params": params},
                    "payload_hash": payload_hash(action, params),
                    "risk_class": "external" if a["risk"] == "external" else "internal_write",
                    "assignee_role": a.get("assignee_role", "ops"),
                    "status": a["status"],
                    "decided_by": self.ref("user", a.get("decided_by")),
                    "decided_at": _dt(a.get("decided_at")),
                    "comment": a.get("comment"),
                    "expires_at": _dt(a.get("expires_at")),
                    "created_at": _dt(a.get("created_at")),
                }
            )
        await self.upsert(Approval, rows)

    async def activity(self, events: list[dict[str, Any]]) -> None:
        rows = []
        for e in events:
            kind, key = ("trip", e["trip"]) if e.get("trip") else ("lead", e["lead"])
            rows.append(
                {
                    "id": self.id("audit", e["key"]),
                    "actor_type": e["actor_type"],
                    "actor_id": e["actor_name"],
                    "action": "activity.recorded",
                    "subject_type": kind,
                    "subject_id": self.id(kind, key),
                    "after": {"text": e["text"]},
                    "at": _dt(e["at"]),
                }
            )
        # audit_log is append-only for the app role: insert once, never update.
        await self.upsert(AuditLog, rows, update=False)

    # upsert

    async def upsert(
        self,
        model: type[Any],
        rows: Iterable[dict[str, Any]],
        *,
        update: bool = True,
        count: bool = True,
    ) -> None:
        table = model.__table__
        columns = {c.name for c in table.columns}
        rows = list(rows)
        if count:
            self.report.counts[table.name] = self.report.counts.get(table.name, 0) + len(rows)
        if not rows:
            return
        # Group by key set: one multi-row INSERT needs identical keys, and dropping None lets
        # server defaults apply on insert and leaves existing values alone on update.
        groups: dict[tuple[str, ...], list[dict[str, Any]]] = {}
        for row in rows:
            unknown = set(row) - columns
            if unknown:
                raise KeyError(f"{table.name}: no column(s) {sorted(unknown)}")
            clean = {k: v for k, v in row.items() if v is not None or k == "id"}
            if "tenant_id" in columns:
                clean["tenant_id"] = self.tenant_id
            groups.setdefault(tuple(sorted(clean)), []).append(clean)
        for keys, group in groups.items():
            stmt = pg_insert(table).values(group)
            if update:
                stmt = stmt.on_conflict_do_update(
                    index_elements=[table.c.id],
                    set_={
                        k: stmt.excluded[k]
                        for k in keys
                        if k not in ("id", "tenant_id", "created_at")
                    },
                )
            else:
                stmt = stmt.on_conflict_do_nothing(index_elements=[table.c.id])
            await self.session.execute(stmt)


# ── helpers ────────────────────────────────────────────────────────────────


def _proposed_action(a: Mapping[str, Any]) -> tuple[str, dict[str, Any]]:
    if a.get("action"):  # approvals raised by a flow node: the exact action + inputs it will run
        return a["action"], dict(a.get("params") or {})
    preview = a["details"].get("preview") or {}
    kind = preview.get("kind")
    if kind == "email":
        return "send_email", {k: preview.get(k) for k in ("to", "subject", "body")}
    if kind == "whatsapp":
        return "send_whatsapp", {k: preview.get(k) for k in ("to", "body")}
    if kind == "change":
        changes = a["details"]["payload"]
        return "update_trip_item", {"summary": preview.get("body"), "changes": changes}
    return "custom", {"payload": a["details"]["payload"]}


def _sha256(value: str) -> str:
    return hashlib.sha256(value.encode()).hexdigest()


def _time(value: Any) -> dt_time | None:
    """Fixture times are "HH:MM". Unquoted, YAML 1.1 reads 07:40 as sexagesimal minutes (460)."""
    if value is None:
        return None
    if isinstance(value, int):
        hours, minutes = divmod(value, 60)
        return dt_time(hours, minutes)
    return dt_time.fromisoformat(str(value))


def _requested_at(item: Mapping[str, Any], now: datetime) -> datetime | None:
    if item.get("status") != "requested":
        return None
    hours = 52 if "52 h" in (item.get("alert") or "") else 24
    return now - timedelta(hours=hours)


def _date(value: str | date) -> date:
    return value if isinstance(value, date) else date.fromisoformat(value)


def _opt_date(value: str | date | None) -> date | None:
    return None if value is None else _date(value)


def _dt(value: str | date | datetime | None) -> datetime | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        parsed = value
    elif isinstance(value, date):
        parsed = datetime(value.year, value.month, value.day)
    else:
        parsed = datetime.fromisoformat(value)
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=UTC)
