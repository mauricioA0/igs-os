"""`POST /v1/guide/turns`: one guide turn streamed as Server-Sent Events.

Same event schema as the copilot (start, text, tool_start, tool_end, done, error). Public and
read-only; rate-limited per visitor and covered by the deployment-wide daily model budget.
"""

from __future__ import annotations

import asyncio
import json
from collections.abc import AsyncIterator
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel, Field
from sse_starlette import EventSourceResponse

from igs_common.llm import create_llm
from igs_common.rag import search_knowledge
from igs_core import db
from igs_core.agent.backend import SqlOpsBackend
from igs_core.agent.runtime import AgentEvent, Copilot, TurnRequest
from igs_core.agent.store import SqlConversationStore, SqlTraceSink
from igs_core.deps import CurrentPrincipal
from igs_core.errors import ProblemError
from igs_core.guide.agent import guide_config
from igs_core.ratelimit import demo_rate_limit
from igs_core.repositories import Repositories

router = APIRouter(prefix="/v1/guide", tags=["guide"])

_running: set[asyncio.Task[None]] = set()


class GuideTurnRequest(BaseModel):
    message: str = Field(min_length=1, max_length=2000)
    conversation_id: UUID | None = None
    page: str | None = Field(
        default=None, max_length=300, description="Route the visitor is on, e.g. /ops/approvals."
    )


def build_guide(repos: Repositories) -> Copilot:
    sessions = db.tenant_session
    return Copilot(
        llm=create_llm(),
        backend=SqlOpsBackend(sessions, repos.trips, repos.accounts, knowledge=search_knowledge),
        conversations=SqlConversationStore(sessions),
        traces=SqlTraceSink(sessions),
        model_name="chat",
        config=guide_config(),
    )


def get_guide(request: Request) -> Copilot:
    guide: Copilot | None = getattr(request.app.state, "guide", None)
    if guide is None:
        try:
            guide = build_guide(request.app.state.repos)
        except Exception as exc:
            raise ProblemError(503, "guide-unavailable", "The guide is not configured.") from exc
        request.app.state.guide = guide
    return guide


@router.post(
    "/turns",
    summary="Run one guide turn (SSE)",
    response_description="text/event-stream of guide events",
    dependencies=[Depends(demo_rate_limit("guide-turn", limit=12, window_s=300))],
)
async def guide_turn(
    body: GuideTurnRequest,
    principal: CurrentPrincipal,
    guide: Annotated[Copilot, Depends(get_guide)],
) -> EventSourceResponse:
    note = f"The visitor is on the page {body.page}." if body.page else None
    turn = TurnRequest(message=body.message, conversation_id=body.conversation_id)
    queue: asyncio.Queue[AgentEvent | None] = asyncio.Queue()

    async def produce() -> None:
        try:
            async for event in guide.turn(principal, turn, note=note):
                await queue.put(event)
        finally:
            await queue.put(None)

    task = asyncio.create_task(produce())
    _running.add(task)
    task.add_done_callback(_running.discard)

    async def stream() -> AsyncIterator[dict[str, str]]:
        while (event := await queue.get()) is not None:
            yield {"event": event.type, "data": json.dumps(event.data, default=str)}
        await task

    return EventSourceResponse(stream(), ping=15)
