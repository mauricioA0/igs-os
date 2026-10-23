"""Tools an ``agent`` node may call, with the policy class that decides who may run them.

Each tool wraps a domain action (same handler as the ``action`` node) or knowledge search.
``tool_class`` + ``coach_safe`` feed ``igs_common.domain.tools.decide``; the agent runner turns
``REQUIRE_APPROVAL`` into a durable approval in the workflow before the handler runs.
"""

from __future__ import annotations

import re
from collections.abc import Awaitable, Callable, Iterable
from dataclasses import dataclass
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

from igs_common.domain.tools import ToolClass
from igs_common.domain.tools import ToolSpec as PolicySpec

from .domain_actions import (
    COACH_SAFE_ACTIONS,
    ActionContext,
    DomainActions,
    action_tool_class,
)
from .retrieval import Retriever


@dataclass(frozen=True)
class ToolContext:
    tenant_id: str | None
    execution_id: str
    node_id: str
    iteration: int
    seq: int  # tool call number within the node run, for idempotency

    def action_context(self) -> ActionContext:
        # Each tool call gets its own idempotency scope inside the node run.
        return ActionContext(
            self.tenant_id, self.execution_id, f"{self.node_id}.t{self.seq}", self.iteration
        )


ToolRun = Callable[[BaseModel, ToolContext], Awaitable[Any]]


@dataclass(frozen=True)
class ToolBinding:
    name: str
    description: str
    input_model: type[BaseModel]
    tool_class: ToolClass
    run: ToolRun
    coach_safe: bool = False

    def policy(self, arguments: dict[str, Any] | None = None) -> PolicySpec:
        # Some actions change class with their inputs (cancelling a trip is destructive).
        cls = self.tool_class
        if self.name == "set_trip_status":
            cls = action_tool_class(self.name, arguments)
        return PolicySpec(name=self.name, tool_class=cls, coach_safe=self.coach_safe)


class _Args(BaseModel):
    model_config = ConfigDict(extra="forbid")


class TripRef(_Args):
    tripId: str = Field(description="Trip id (UUID).")


class ListItems(_Args):
    tripId: str
    statuses: list[Literal["pending", "requested", "confirmed", "cancelled"]] | None = None
    withProvider: bool | None = None


class UpdateItem(_Args):
    itemId: str
    status: Literal["pending", "requested", "confirmed", "cancelled"] | None = None
    notes: str | None = None


class SwapOpponent(_Args):
    itemId: str
    opponentId: str


class SetTripStatus(_Args):
    tripId: str
    status: Literal["draft", "proposed", "confirmed", "in_progress", "completed", "cancelled"]


class LeadIn(_Args):
    sport: Literal["soccer", "rugby", "field_hockey", "volleyball", "basketball"]
    gender: Literal["men", "women", "mixed"]
    ageGroup: str = Field(description="U13, U15, U17, U19 or college.")
    levelScore: int = Field(ge=1, le=10, description="1 recreational … 10 professional academy.")
    groupSize: int = Field(ge=1, le=80)
    destinationCountry: Literal["Argentina", "Brazil", "Costa Rica"]
    travelStart: str = Field(description="YYYY-MM-DD")
    durationDays: int = Field(ge=3, le=21)
    budgetPerPersonUsd: int | None = None
    goals: str | None = None


class CreateLead(_Args):
    lead: LeadIn


class LeadRef(_Args):
    leadId: str


class RequestConfirmations(_Args):
    tripId: str
    replyBy: str = Field(description="ISO timestamp providers must answer by.")


class SendProposal(_Args):
    tripId: str
    to: str = Field(description="Coach email.")
    note: str | None = None


class OpsTask(_Args):
    title: str
    tripId: str | None = None
    details: str | None = None


class FindOpponents(_Args):
    sport: Literal["soccer", "rugby", "field_hockey", "volleyball", "basketball"]
    gender: Literal["men", "women", "mixed"]
    ageGroup: str | None = None
    levelScore: int | None = Field(default=None, ge=1, le=10)
    country: Literal["Argentina", "Brazil", "Costa Rica"] | None = None


class FindExperiences(_Args):
    country: Literal["Argentina", "Brazil", "Costa Rica"]
    sport: str | None = None


class SearchKnowledge(_Args):
    query: str
    country: str | None = None


_ACTION_TOOLS: list[tuple[str, str, type[BaseModel]]] = [
    ("get_trip", "Read a trip with its lead and day-by-day items.", TripRef),
    (
        "find_opponents",
        "Opponents of the right sport, gender and age, closest level first.",
        FindOpponents,
    ),
    (
        "find_experiences",
        "Cultural and sports experiences available in a country.",
        FindExperiences,
    ),
    ("list_trip_items", "List a trip's items, optionally filtered by status.", ListItems),
    ("update_trip_item", "Change an item's status or notes (internal).", UpdateItem),
    ("swap_opponent", "Replace the opponent of a match item.", SwapOpponent),
    ("set_trip_status", "Move a trip to another status. Cancelling needs approval.", SetTripStatus),
    ("create_lead", "Create a qualified lead from what the coach told you.", CreateLead),
    ("draft_trip", "Plan and price a trip proposal for a lead.", LeadRef),
    (
        "request_provider_confirmations",
        "Ask every provider of a trip to confirm (sends messages; needs approval).",
        RequestConfirmations,
    ),
    ("send_proposal", "Email the trip proposal to the coach (needs approval).", SendProposal),
    ("create_ops_task", "Hand something to the ops team.", OpsTask),
]


def _action_runner(actions: DomainActions, action: str) -> ToolRun:
    async def run(args: BaseModel, ctx: ToolContext) -> Any:
        inputs = args.model_dump(exclude_none=True)
        if action == "create_ops_task" and "details" in inputs:
            inputs["context"] = inputs.pop("details")
        return await actions.run(action, inputs, ctx.action_context())

    return run


def _search_runner(retriever: Retriever) -> ToolRun:
    async def run(args: BaseModel, ctx: ToolContext) -> Any:
        assert isinstance(args, SearchKnowledge)
        if ctx.tenant_id is None:
            raise ValueError("knowledge search needs a tenant")
        # Knowledge documents only. Client interactions (emails, call notes, rosters with minors'
        # passports) are indexed in the same store for Account 360, and this tool also serves the
        # public coach chat: without this filter any visitor could retrieve them.
        filters: dict[str, Any] = {"source_kind": {"$eq": "document"}}
        # Country steers the query instead of filtering: most knowledge documents (pricing,
        # entry requirements) carry no country metadata, and a hard filter returned nothing.
        query = f"{args.query} {args.country}" if args.country else args.query
        result = await retriever.search(
            query,
            tenant_id=ctx.tenant_id,
            knowledge_bases=(),
            filters=filters,
            k=5,
            rerank=True,
        )
        return {
            "hits": [
                {"content": h.get("content", ""), "citation": h.get("citation") or _cite(h)}
                for h in result.get("hits", [])
            ]
        }

    return run


def _cite(hit: dict[str, Any]) -> str | None:
    # RAG hits carry no citation id; the document title slug ("cancellation-policy") is stable
    # and readable. Without one the model can't cite and answers look ungrounded.
    title = str(hit.get("title") or "")
    slug = re.sub(r"[^a-z0-9]+", "-", title.lower()).strip("-")
    return slug or None


class ToolRegistry:
    def __init__(self, bindings: Iterable[ToolBinding]) -> None:
        self._by_name = {b.name: b for b in bindings}

    def get(self, name: str) -> ToolBinding | None:
        return self._by_name.get(name)

    def select(self, names: Iterable[str]) -> list[ToolBinding]:
        missing = [n for n in names if n not in self._by_name]
        if missing:
            raise KeyError(f"unknown tools: {', '.join(missing)}")
        return [self._by_name[n] for n in names]

    @property
    def names(self) -> list[str]:
        return sorted(self._by_name)


def default_registry(actions: DomainActions, retriever: Retriever) -> ToolRegistry:
    bindings = [
        ToolBinding(
            name=name,
            description=description,
            input_model=model,
            tool_class=action_tool_class(name),
            run=_action_runner(actions, name),
            coach_safe=name in COACH_SAFE_ACTIONS,
        )
        for name, description, model in _ACTION_TOOLS
    ]
    bindings.append(
        ToolBinding(
            name="search_knowledge",
            description="Search IGS policies, destinations, opponents and past trips; cite hits.",
            input_model=SearchKnowledge,
            tool_class=ToolClass.READ,
            run=_search_runner(retriever),
        )
    )
    return ToolRegistry(bindings)
