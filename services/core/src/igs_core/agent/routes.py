"""`POST /v1/copilot/turns`: one copilot turn streamed as Server-Sent Events.

Event names: start, text, tool_start, tool_end, approval_required, done, error. Each `data` is
JSON. The turn keeps running to completion if the client disconnects mid-stream (it is drained
in the background), so history and traces stay consistent.
"""

from __future__ import annotations

import asyncio
import json
from collections.abc import AsyncIterator
from typing import Annotated

from fastapi import APIRouter, Depends, Request
from sse_starlette import EventSourceResponse

from igs_common.llm import create_llm
from igs_common.rag import search_knowledge
from igs_core import db
from igs_core.agent.backend import SqlOpsBackend
from igs_core.agent.runtime import AgentEvent, Copilot, TurnRequest
from igs_core.agent.store import SqlConversationStore, SqlTraceSink
from igs_core.deps import CurrentPrincipal
from igs_core.errors import ProblemError
from igs_core.ratelimit import demo_rate_limit
from igs_core.repositories import Repositories

router = APIRouter(prefix="/v1/copilot", tags=["copilot"])

# Strong references so turns drained after a disconnect aren't garbage-collected mid-run.
_running: set[asyncio.Task[None]] = set()


def build_copilot(repos: Repositories) -> Copilot:
    """Production wiring: OpenAI (per IGS_LLM_MODELS) + SQL backend, history and traces."""
    sessions = db.tenant_session
    return Copilot(
        llm=create_llm(),
        backend=SqlOpsBackend(sessions, repos.trips, repos.accounts, knowledge=search_knowledge),
        conversations=SqlConversationStore(sessions),
        traces=SqlTraceSink(sessions),
    )


def get_copilot(request: Request) -> Copilot:
    copilot: Copilot | None = getattr(request.app.state, "copilot", None)
    if copilot is None:
        try:
            copilot = build_copilot(request.app.state.repos)
        except Exception as exc:  # misconfigured model settings must not take the API down
            raise ProblemError(
                503, "copilot-unavailable", "The copilot is not configured."
            ) from exc
        request.app.state.copilot = copilot
    return copilot


@router.post(
    "/turns",
    summary="Run one copilot turn (SSE)",
    response_description="text/event-stream of copilot events",
    # Each turn spends model tokens: cap the anonymous demo (S-03).
    dependencies=[Depends(demo_rate_limit("copilot-turn", limit=10, window_s=300))],
)
async def copilot_turn(
    body: TurnRequest,
    principal: CurrentPrincipal,
    copilot: Annotated[Copilot, Depends(get_copilot)],
) -> EventSourceResponse:
    queue: asyncio.Queue[AgentEvent | None] = asyncio.Queue()

    async def produce() -> None:
        try:
            async for event in copilot.turn(principal, body):
                await queue.put(event)
        finally:
            await queue.put(None)

    # Shielded from client disconnects: the turn finishes and persists either way.
    task = asyncio.create_task(produce())
    _running.add(task)
    task.add_done_callback(_running.discard)

    async def stream() -> AsyncIterator[dict[str, str]]:
        while (event := await queue.get()) is not None:
            yield {"event": event.type, "data": json.dumps(event.data, default=str)}
        await task

    return EventSourceResponse(stream(), ping=15)
