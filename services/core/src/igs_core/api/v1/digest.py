"""Morning ops digest: the Hoy screen as a short, prioritized brief (JSON, HTML email, text).

Facts are deterministic (igs_common.digest). The opening lines are phrased by a model when one
is configured, checked number by number against the facts, and cached per tenant until the
facts change, so refreshing the page or the public demo never re-spends tokens.
"""

import hashlib
import json
from datetime import UTC, datetime
from typing import Any, Literal
from uuid import UUID

import structlog
from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse, PlainTextResponse, Response
from pydantic import BaseModel, Field

from igs_common.digest import Digest, Phrased, build_digest, phrase_summary
from igs_common.digest.load import load_digest_inputs
from igs_common.llm import LLMClient, LLMSettings, create_llm
from igs_core.deps import AppSettings, CurrentPrincipal
from igs_core.runtime import SessionFactory, Sessions

router = APIRouter(prefix="/digest", tags=["digest"])
log = structlog.get_logger("igs_core.digest")


class DigestOut(BaseModel):
    summary: str = Field(description="2–3 sentences. Every number in it exists in `facts`.")
    summary_source: Literal["llm", "template"]
    summary_model: str | None
    facts: dict[str, Any] = Field(description="Risks, payments, approvals, departures, leads.")
    text: str = Field(description="Plain-text rendering (email fallback, chat, logs).")


def digest_llm(request: Request) -> LLMClient | None:
    """`app.state.llm` (tests) or the configured provider; None → template summary."""
    llm = getattr(request.app.state, "llm", None)
    if llm is not None:
        return llm  # type: ignore[no-any-return]
    try:
        settings = LLMSettings()
        return create_llm(settings) if settings.openai_api_key is not None else None
    except Exception:  # a misconfigured model must not take the digest down
        log.warning("digest_llm_unavailable", exc_info=True)
        return None


async def build_today(
    request: Request, tenant_id: UUID, sessions: SessionFactory, base_url: str
) -> Digest:
    now = datetime.now(UTC)
    async with sessions(tenant_id) as session:
        inputs = await load_digest_inputs(session, tenant_id=tenant_id, now=now)
    facts = build_digest(inputs, now=now)
    cache: dict[tuple[str, str], Phrased] | None = getattr(
        request.app.state, "digest_summaries", None
    )
    if cache is None:
        cache = request.app.state.digest_summaries = {}
    stable = facts.to_json()
    stable.pop("generated_at", None)
    for a in stable["approvals"]:  # hour counters tick; the substance doesn't
        a.pop("waiting_hours", None)
        a.pop("expires_in_hours", None)
    key = (str(tenant_id), hashlib.sha256(json.dumps(stable, sort_keys=True).encode()).hexdigest())
    phrased = cache.get(key)
    if phrased is None:
        phrased = await phrase_summary(digest_llm(request), facts)
        if len(cache) > 256:
            cache.clear()
        cache[key] = phrased
    return Digest(facts=facts, phrased=phrased, base_url=base_url.rstrip("/"))


@router.get(
    "/today",
    response_model=DigestOut,
    summary="Morning ops digest: top risks, payments, approvals, departures, unanswered leads",
    responses={200: {"content": {"text/html": {}, "text/plain": {}}}},
)
async def digest_today(
    request: Request,
    principal: CurrentPrincipal,
    sessions: Sessions,
    settings: AppSettings,
    format: Literal["json", "html", "text"] = "json",
) -> Response | DigestOut:
    digest = await build_today(request, principal.tenant_id, sessions, settings.web_base_url)
    if format == "html":
        return HTMLResponse(digest.html())
    if format == "text":
        return PlainTextResponse(digest.text())
    data = digest.json()
    return DigestOut(**data, text=digest.text())
