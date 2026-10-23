"""Flows: draft editing with optimistic concurrency, validation and immutable publishing.

- The draft lives on ``flows.draft_graph``; every save bumps ``draft_revision``. Saves and
  publishes require ``If-Match`` with the revision the editor loaded (412 when stale, 428 when
  missing). Responses carry it as ``ETag: "rev-<n>"``.
- Publishing validates with ``igs_common.flows.validate`` (graph rules + the untrusted-trigger
  security rule), then snapshots the draft into a new immutable ``flow_versions`` row and
  re-derives ``flow_triggers``. Executions pin a version, so publishing never changes runs
  already in flight.
"""

import hashlib
from typing import Annotated, Any
from uuid import UUID

from fastapi import APIRouter, Header, Response
from sqlalchemy import delete, func, select

from igs_common.db.enums import TriggerKind
from igs_common.db.models import Flow, FlowTrigger, FlowVersion
from igs_common.domain.approvals import canonical_json
from igs_common.flows.validate import ValidationResult, validate_flow
from igs_core.deps import CurrentPrincipal
from igs_core.errors import ProblemError
from igs_core.events import audit, emit
from igs_core.runtime import RequestId, Sessions, Writer
from igs_core.schemas.workflows import (
    FlowCreateIn,
    FlowDetail,
    FlowDraftIn,
    FlowSummary,
    FlowVersionOut,
    PublishIn,
    ValidationOut,
    ValidationProblem,
)

router = APIRouter(prefix="/flows", tags=["flows"])

IfMatch = Annotated[str | None, Header(alias="If-Match")]


def etag(revision: int) -> str:
    return f'"rev-{revision}"'


def _parse_if_match(value: str | None) -> int:
    if not value:
        raise ProblemError(428, "precondition-required", "Send If-Match with the draft revision.")
    raw = value.strip().removeprefix("W/").strip('"').removeprefix("rev-")
    try:
        return int(raw)
    except ValueError as exc:
        raise ProblemError(400, "invalid-if-match", 'If-Match must be "rev-<n>".') from exc


def _validation_out(result: ValidationResult) -> ValidationOut:
    return ValidationOut(
        ok=result.ok,
        problems=[
            ValidationProblem(
                code=p.code,
                message=p.message,
                severity=p.severity,
                node_id=p.node_id,
                path=p.path,
            )
            for p in result.problems
        ],
    )


async def _published_version(session: Any, flow: Flow) -> int | None:
    if flow.published_version_id is None:
        return None
    return await session.scalar(
        select(FlowVersion.version).where(FlowVersion.id == flow.published_version_id)
    )


async def _summary(session: Any, flow: Flow) -> FlowSummary:
    return FlowSummary(
        id=flow.id,
        key=flow.key,
        name=flow.name,
        description=flow.description or "",
        draft_revision=flow.draft_revision,
        published_version=await _published_version(session, flow),
        updated_at=flow.updated_at,
        archived_at=flow.archived_at,
    )


async def _detail(session: Any, flow: Flow) -> FlowDetail:
    summary = await _summary(session, flow)
    return FlowDetail(**summary.model_dump(), draft_graph=flow.draft_graph)


async def _load(session: Any, flow_id: UUID, *, lock: bool = False) -> Flow:
    query = select(Flow).where(Flow.id == flow_id)
    if lock:
        query = query.with_for_update()
    flow = await session.scalar(query)
    if flow is None:
        raise ProblemError(404, "not-found", "Flow not found.")
    return flow


def _check_key(flow_key: str, graph: dict[str, Any]) -> None:
    if graph.get("id") != flow_key:
        raise ProblemError(422, "flow-key-mismatch", f"graph.id must be {flow_key!r}.")


@router.get("", response_model=list[FlowSummary], summary="List flows")
async def list_flows(
    principal: CurrentPrincipal, sessions: Sessions, include_archived: bool = False
) -> list[FlowSummary]:
    query = select(Flow).order_by(Flow.name, Flow.id)
    if not include_archived:
        query = query.where(Flow.archived_at.is_(None))
    async with sessions(principal.tenant_id) as session:
        return [await _summary(session, f) for f in (await session.scalars(query)).all()]


@router.post("", response_model=FlowDetail, status_code=201, summary="Create a flow draft")
async def create_flow(
    body: FlowCreateIn,
    principal: Writer,
    sessions: Sessions,
    response: Response,
    rid: RequestId,
) -> FlowDetail:
    key = body.graph.get("id")
    if not isinstance(key, str) or not key:
        raise ProblemError(422, "missing-flow-id", "graph.id (the flow key) is required.")
    async with sessions(principal.tenant_id) as session:
        exists = await session.scalar(select(Flow.id).where(Flow.key == key))
        if exists is not None:
            raise ProblemError(409, "flow-exists", f"A flow with key {key!r} already exists.")
        flow = Flow(
            tenant_id=principal.tenant_id,
            key=key,
            name=body.name,
            description=body.description,
            draft_graph=body.graph,
        )
        session.add(flow)
        await session.flush()
        await audit(
            session,
            principal,
            action="flow.created",
            subject_type="flow",
            subject_id=flow.id,
            request_id=rid,
        )
        await session.refresh(flow)
        out = await _detail(session, flow)
    response.headers["ETag"] = etag(out.draft_revision)
    return out


@router.get("/{flow_id}", response_model=FlowDetail, summary="Get a flow with its draft")
async def get_flow(
    flow_id: UUID, principal: CurrentPrincipal, sessions: Sessions, response: Response
) -> FlowDetail:
    async with sessions(principal.tenant_id) as session:
        out = await _detail(session, await _load(session, flow_id))
    response.headers["ETag"] = etag(out.draft_revision)
    return out


@router.put("/{flow_id}/draft", response_model=FlowDetail, summary="Save the draft (If-Match)")
async def save_draft(
    flow_id: UUID,
    body: FlowDraftIn,
    principal: Writer,
    sessions: Sessions,
    response: Response,
    rid: RequestId,
    if_match: IfMatch = None,
) -> FlowDetail:
    expected = _parse_if_match(if_match)
    async with sessions(principal.tenant_id) as session:
        flow = await _load(session, flow_id, lock=True)
        if flow.draft_revision != expected:
            raise ProblemError(
                412,
                "stale-draft",
                f"The draft is at revision {flow.draft_revision}; reload before saving.",
                headers={"ETag": etag(flow.draft_revision)},
            )
        _check_key(flow.key, body.graph)
        flow.draft_graph = body.graph
        flow.draft_revision += 1
        flow.draft_updated_by = None
        if body.name is not None:
            flow.name = body.name
        if body.description is not None:
            flow.description = body.description
        await audit(
            session,
            principal,
            action="flow.draft_saved",
            subject_type="flow",
            subject_id=flow.id,
            after={"revision": flow.draft_revision},
            request_id=rid,
        )
        await session.flush()
        await session.refresh(flow)
        out = await _detail(session, flow)
    response.headers["ETag"] = etag(out.draft_revision)
    return out


@router.post(
    "/{flow_id}/validate",
    response_model=ValidationOut,
    summary="Validate the draft (or a graph in the body) without saving",
)
async def validate_draft(
    flow_id: UUID,
    principal: CurrentPrincipal,
    sessions: Sessions,
    body: FlowDraftIn | None = None,
) -> ValidationOut:
    async with sessions(principal.tenant_id) as session:
        flow = await _load(session, flow_id)
        graph = body.graph if body is not None else flow.draft_graph
    return _validation_out(validate_flow(graph))


@router.post(
    "/{flow_id}/publish",
    response_model=FlowVersionOut,
    status_code=201,
    summary="Publish the draft as a new immutable version (If-Match)",
)
async def publish(
    flow_id: UUID,
    principal: Writer,
    sessions: Sessions,
    rid: RequestId,
    body: PublishIn | None = None,
    if_match: IfMatch = None,
) -> FlowVersionOut:
    expected = _parse_if_match(if_match)
    async with sessions(principal.tenant_id) as session:
        flow = await _load(session, flow_id, lock=True)
        if flow.draft_revision != expected:
            raise ProblemError(
                412,
                "stale-draft",
                f"The draft is at revision {flow.draft_revision}; reload before publishing.",
                headers={"ETag": etag(flow.draft_revision)},
            )
        _check_key(flow.key, flow.draft_graph)
        result = validate_flow(flow.draft_graph)
        if not result.ok:
            raise ProblemError(
                422,
                "flow-invalid",
                f"{len(result.errors)} problem(s) block publishing.",
                errors=[p.model_dump() for p in _validation_out(result).problems],
            )
        latest = await session.scalar(
            select(func.max(FlowVersion.version)).where(FlowVersion.flow_id == flow.id)
        )
        version_no = (latest or 0) + 1
        graph = {**flow.draft_graph, "version": version_no}
        version = FlowVersion(
            tenant_id=principal.tenant_id,
            flow_id=flow.id,
            version=version_no,
            graph=graph,
            graph_hash=hashlib.sha256(canonical_json(graph).encode()).hexdigest(),
            schema_version=str(graph.get("schemaVersion", "1")),
            changelog=body.changelog if body else "",
        )
        session.add(version)
        await session.flush()
        flow.published_version_id = version.id

        trigger = graph.get("trigger") or {}
        await session.execute(delete(FlowTrigger).where(FlowTrigger.flow_id == flow.id))
        if trigger.get("type") in {k.value for k in TriggerKind}:
            session.add(
                FlowTrigger(
                    tenant_id=principal.tenant_id,
                    flow_id=flow.id,
                    kind=TriggerKind(trigger["type"]),
                    config=trigger,
                )
            )
        await audit(
            session,
            principal,
            action="flow.published",
            subject_type="flow",
            subject_id=flow.id,
            after={"version": version_no, "graph_hash": version.graph_hash},
            request_id=rid,
        )
        await emit(
            session,
            tenant_id=principal.tenant_id,
            type="flow.published",
            subject_type="flow",
            subject_id=flow.id,
            payload={"flow": {"id": str(flow.id), "key": flow.key, "version": version_no}},
        )
        await session.flush()
        await session.refresh(version)
        return FlowVersionOut.model_validate(version)


@router.get(
    "/{flow_id}/versions", response_model=list[FlowVersionOut], summary="Published versions"
)
async def list_versions(
    flow_id: UUID, principal: CurrentPrincipal, sessions: Sessions
) -> list[FlowVersionOut]:
    async with sessions(principal.tenant_id) as session:
        await _load(session, flow_id)
        rows = (
            await session.scalars(
                select(FlowVersion)
                .where(FlowVersion.flow_id == flow_id)
                .order_by(FlowVersion.version.desc())
            )
        ).all()
        return [FlowVersionOut.model_validate(r).model_copy(update={"graph": None}) for r in rows]


@router.get(
    "/{flow_id}/versions/{version}",
    response_model=FlowVersionOut,
    summary="One published version with its graph",
)
async def get_version(
    flow_id: UUID, version: int, principal: CurrentPrincipal, sessions: Sessions
) -> FlowVersionOut:
    async with sessions(principal.tenant_id) as session:
        row = await session.scalar(
            select(FlowVersion).where(
                FlowVersion.flow_id == flow_id, FlowVersion.version == version
            )
        )
        if row is None:
            raise ProblemError(404, "not-found", "Version not found.")
        return FlowVersionOut.model_validate(row)
