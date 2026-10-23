"""In-memory OpsBackend and principals for copilot/MCP tests (unique module name on purpose)."""

from typing import Any
from uuid import UUID, uuid4

from igs_core.agent.backend import Actor, ApprovalRequest
from igs_core.repositories.base import Principal

TENANT = UUID("00000000-0000-0000-0000-0000000000c1")
OTHER = UUID("00000000-0000-0000-0000-0000000000c2")
TRIP_ID = UUID("00000000-0000-0000-0000-000000002711")
ITEM_ID = UUID("00000000-0000-0000-0000-0000000027a1")
ACCOUNT_ID = UUID("00000000-0000-0000-0000-0000000000a7")
INTERACTION_ID = UUID("00000000-0000-0000-0000-0000000000f1")
TRAVELER_ID = UUID("00000000-0000-0000-0000-0000000000b1")


def principal(kind: str = "user", role: str = "ops", scopes: set[str] | None = None) -> Principal:
    return Principal(
        kind=kind,  # type: ignore[arg-type]
        tenant_id=TENANT,
        role=role,  # type: ignore[arg-type]
        subject=f"{kind}:test",
        scopes=frozenset(scopes or ()),
    )


class FakeOpsBackend:
    def __init__(self, tenant: UUID = TENANT) -> None:
        self.tenant = tenant
        self.trip = {
            "id": str(TRIP_ID),
            "code": "IGS-2711",
            "title": "Lakeshore University Women's Soccer · Buenos Aires",
            "status": "proposed",
            "team": {"coach_name": "Coach Dana Whitfield"},
            "items": [{"id": str(ITEM_ID), "day": 3, "status": "pending", "title": "Referees"}],
        }
        self.items = {ITEM_ID: {"id": str(ITEM_ID), "status": "pending", "notes": None}}
        self.approvals: list[tuple[UUID, ApprovalRequest, Actor]] = []
        self.updates: list[tuple[UUID, Actor]] = []
        self.document_updates: list[tuple[UUID, str, str, Actor]] = []
        self.account = {
            "id": str(ACCOUNT_ID),
            "name": "Lakeshore University",
            "kind": "university",
            "status": "active",
            "health": "amber",
            "city": "Chicago",
            "stakeholders": [
                {"name": "Robert Haines", "role": "decision_maker", "influence": 5},
                {"name": "Dana Whitfield", "role": "coach", "influence": 4},
            ],
            "facts": [
                {
                    "kind": "risk",
                    "statement": "Budget approval pending from the AD.",
                    "source_interaction_id": str(INTERACTION_ID),
                }
            ],
            "recent_interactions": [],
        }

    def _check(self, tenant_id: UUID) -> None:
        assert tenant_id == self.tenant, "tenant leaked into the backend call"

    async def list_trips(self, tenant_id, *, status, departing_from, limit) -> list[dict[str, Any]]:
        self._check(tenant_id)
        return [self.trip][:limit]

    async def get_trip(self, tenant_id, trip_id) -> dict[str, Any] | None:
        self._check(tenant_id)
        return self.trip if trip_id == TRIP_ID else None

    async def list_unconfirmed_items(
        self, tenant_id, *, trip_id, departing_within_days, limit
    ) -> list[dict[str, Any]]:
        self._check(tenant_id)
        return [i for i in self.items.values() if i["status"] in ("pending", "requested")]

    async def update_trip_item(self, tenant_id, item_id, *, status, notes, actor):
        self._check(tenant_id)
        item = self.items.get(item_id)
        if item is None:
            return None
        if status:
            item["status"] = status
        if notes is not None:
            item["notes"] = notes
        self.updates.append((item_id, actor))
        return item

    async def trip_readiness(self, tenant_id, trip_id):
        self._check(tenant_id)
        if trip_id != TRIP_ID:
            return None
        item = {"requirement": "passport", "state": "missing", "blocking": True, "warnings": []}
        return {
            "trip": {"id": str(TRIP_ID), "code": "IGS-2711"},
            "ready": False,
            "open_items": 1,
            "people": [
                {"traveler_id": str(TRAVELER_ID), "full_name": "Ana", "ready": False,
                 "items": [item, item | {"requirement": "x", "blocking": False, "state": "ok"}]},
            ],
        }  # fmt: skip

    async def update_traveler_document(
        self, tenant_id, traveler_id, requirement, *, status, valid_from, valid_until, note, actor
    ):
        self._check(tenant_id)
        if traveler_id != TRAVELER_ID:
            return None
        self.document_updates.append((traveler_id, requirement, status, actor))
        return {"traveler_id": str(traveler_id), "requirement": requirement, "status": status}

    async def find_accounts(self, tenant_id, *, query, health, limit):
        self._check(tenant_id)
        return [{"id": self.account["id"], "name": self.account["name"]}]

    async def get_account(self, tenant_id, account_id):
        self._check(tenant_id)
        return self.account if account_id == ACCOUNT_ID else None

    async def search_account_history(self, tenant_id, account_id, *, query, limit):
        self._check(tenant_id)
        return [{"id": str(INTERACTION_ID), "citation": f"interaction:{INTERACTION_ID}"}]

    async def list_payment_risks(self, tenant_id, *, account_id, trip_id, within_days, limit):
        self._check(tenant_id)
        risk = {
            "trip_id": str(TRIP_ID),
            "trip_code": "IGS-2711",
            "account": "Lakeshore University",
            "kind": "enrollment",
            "due": "2026-10-15",
            "days": -7,
            "stage": "overdue_7",
            "seats": 24,
            "outstanding_usd": 2280,
        }
        return {"as_of": "2026-10-22", "overdue_usd": 2280, "risks": [risk][:limit]}

    async def list_pending_approvals(self, tenant_id, *, limit):
        self._check(tenant_id)
        return [{"id": str(a_id), "title": r.title} for a_id, r, _ in self.approvals][:limit]

    async def create_approval(self, tenant_id, request: ApprovalRequest, actor: Actor):
        self._check(tenant_id)
        approval_id = uuid4()
        self.approvals.append((approval_id, request, actor))
        return {"id": approval_id, "title": request.title, "payload_hash": request.payload_hash}

    async def list_flows(self, tenant_id):
        self._check(tenant_id)
        return [{"key": "inbound-inquiry", "name": "Inbound inquiry"}]

    async def run_flow_test(self, tenant_id, flow_key, payload, actor):
        self._check(tenant_id)
        return {"execution_id": "ex-test", "flow_key": flow_key, "mode": payload.get("mode")}

    async def daily_digest(self, tenant_id):
        self._check(tenant_id)
        return {"summary": "Lo primero: Lakeshore University.", "facts": {"risks": []}}

    async def search_knowledge(self, tenant_id, query, k):
        self._check(tenant_id)
        return [{"title": "Cancellation policy", "citation": "chunk:1", "content": "30 days"}]
