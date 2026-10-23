"""Account 360 AI: cited brief and "ask about this client". Mounted under /v1 by app wiring."""

from datetime import datetime
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel, Field

from igs_common.accounts import (
    AccountIntelligence,
    AccountNotFoundError,
    Answer,
    Brief,
    Citation,
    RagRetriever,
)
from igs_common.llm import LLMError, LLMSettings, ModelRegistry, create_llm
from igs_core import db
from igs_core.deps import CurrentPrincipal
from igs_core.errors import ProblemError
from igs_core.ratelimit import demo_rate_limit

router = APIRouter(prefix="/accounts", tags=["accounts"])


class CitationOut(BaseModel):
    n: int
    interaction_id: UUID | None = Field(description="None when the source is the system record.")
    label: str


class BriefOut(BaseModel):
    account_id: UUID
    text: str = Field(description="4–6 sentences with [n] markers that index `citations`.")
    citations: list[CitationOut]
    health: str
    health_reasons: list[str]
    generated_at: datetime
    model: str
    cached: bool


class AskIn(BaseModel):
    question: str = Field(min_length=3, max_length=1000)


class AskOut(BaseModel):
    question: str
    text: str
    citations: list[CitationOut]
    grounded: bool = Field(description="False when the answer is an abstention.")
    model: str


def get_account_intelligence(request: Request) -> AccountIntelligence:
    """Built once per app. `app.state.llm` / `app.state.retriever` override the defaults."""
    service: AccountIntelligence | None = getattr(request.app.state, "account_intelligence", None)
    if service is None:
        llm = getattr(request.app.state, "llm", None)
        try:
            settings = LLMSettings()
            if llm is None and settings.openai_api_key is None:
                raise ValueError("no model provider key configured")
            registry = ModelRegistry(settings.models)
            llm = llm or create_llm(settings)
        except Exception as exc:  # misconfigured model settings must not take the API down
            raise ProblemError(
                503, "ai-unavailable", "Account intelligence is not configured."
            ) from exc
        service = AccountIntelligence(
            llm=llm,
            retriever=getattr(request.app.state, "retriever", None) or RagRetriever(),
            session_factory=db.tenant_session,
            model_for=registry.model_for,
        )
        request.app.state.account_intelligence = service
    return service


Intelligence = Annotated[AccountIntelligence, Depends(get_account_intelligence)]


@router.get(
    "/{account_id}/brief",
    response_model=BriefOut,
    summary="Cited account brief (cached until its inputs change)",
)
async def get_brief(
    account_id: UUID, principal: CurrentPrincipal, service: Intelligence, refresh: bool = False
) -> BriefOut:
    if refresh and principal.kind == "demo":
        raise ProblemError(403, "forbidden", "The public demo can't force a brief refresh.")
    try:
        brief, cached = await service.brief(
            tenant_id=principal.tenant_id, account_id=account_id, refresh=refresh
        )
    except AccountNotFoundError:
        raise ProblemError(404, "not-found", "Account not found.") from None
    except LLMError:
        raise ProblemError(502, "llm-unavailable", "The brief could not be generated.") from None
    return _brief_out(brief, cached)


@router.post(
    "/{account_id}/ask",
    response_model=AskOut,
    summary="Ask about this client: cited answer, or an abstention when not grounded",
    # Each question spends model tokens: cap the anonymous demo (S-03).
    dependencies=[Depends(demo_rate_limit("account-ask", limit=10, window_s=300))],
)
async def ask_account(
    account_id: UUID, body: AskIn, principal: CurrentPrincipal, service: Intelligence
) -> AskOut:
    try:
        answer = await service.ask(
            tenant_id=principal.tenant_id, account_id=account_id, question=body.question
        )
    except AccountNotFoundError:
        raise ProblemError(404, "not-found", "Account not found.") from None
    except LLMError:
        raise ProblemError(502, "llm-unavailable", "The question could not be answered.") from None
    return _answer_out(answer)


def _citations(citations: tuple[Citation, ...]) -> list[CitationOut]:
    return [CitationOut(n=c.n, interaction_id=c.interaction_id, label=c.label) for c in citations]


def _brief_out(brief: Brief, cached: bool) -> BriefOut:
    return BriefOut(
        account_id=brief.account_id,
        text=brief.text,
        citations=_citations(brief.citations),
        health=brief.health.value,
        health_reasons=list(brief.health_reasons),
        generated_at=brief.generated_at,
        model=brief.model,
        cached=cached,
    )


def _answer_out(answer: Answer) -> AskOut:
    return AskOut(
        question=answer.question,
        text=answer.text,
        citations=_citations(answer.citations),
        grounded=answer.grounded,
        model=answer.model,
    )
