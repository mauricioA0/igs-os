"""Bulk import of an operator's spreadsheets (accounts, stakeholders, trips, travelers…).

The body is the raw file (``.xlsx`` or ``.csv``), not multipart:

    curl -X POST "$API/v1/imports?filename=clientes.xlsx" -H "Authorization: Bearer igs_…" \\
         --data-binary @clientes.xlsx

``dry_run`` defaults to true: the response says exactly what would be created or updated, row
by row. Re-send with ``dry_run=false`` to write it (all or nothing; nothing is ever deleted).
Admins only: owners, or API keys with the ``igs:admin`` scope.
"""

from typing import Annotated, Literal

from fastapi import APIRouter, Depends, Query, Request

from igs_common.importer import Entity, ImportFileError, ImportReport, import_file
from igs_common.llm import LLMClient, LLMSettings, create_llm
from igs_core.deps import AppSettings, CurrentPrincipal
from igs_core.errors import ProblemError
from igs_core.events.outbox import actor_of
from igs_core.repositories import Principal
from igs_core.runtime import RequestId, Sessions

SCOPE_ADMIN = "igs:admin"

router = APIRouter(prefix="/imports", tags=["imports"])


def require_admin(principal: CurrentPrincipal) -> Principal:
    if principal.kind == "demo":
        raise ProblemError(403, "read-only-demo", "The public demo is read-only.")
    if principal.kind == "api_key":
        if SCOPE_ADMIN not in principal.scopes:
            raise ProblemError(403, "forbidden", f"Imports need the {SCOPE_ADMIN} scope.")
    elif principal.role != "owner":
        raise ProblemError(403, "forbidden", "Only owners can import data.")
    return principal


Admin = Annotated[Principal, Depends(require_admin)]


def _mapper(request: Request, settings: AppSettings, wanted: bool) -> LLMClient | None:
    if not wanted:
        return None
    if not settings.import_llm_mapping:
        raise ProblemError(
            409, "llm-mapping-disabled", "The AI column mapper is off in this deployment."
        )
    llm = getattr(request.app.state, "llm", None)
    if llm is None:
        try:
            llm_settings = LLMSettings()
            if llm_settings.openai_api_key is None:
                raise ValueError("no model provider key configured")
            llm = create_llm(llm_settings)
        except Exception as exc:
            raise ProblemError(503, "ai-unavailable", "No model is configured.") from exc
    return llm


@router.post(
    "",
    response_model=ImportReport,
    summary="Import a spreadsheet (dry run by default)",
    openapi_extra={
        "requestBody": {
            "required": True,
            "content": {
                "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet": {
                    "schema": {"type": "string", "format": "binary"}
                },
                "text/csv": {"schema": {"type": "string", "format": "binary"}},
            },
        }
    },
)
async def create_import(
    request: Request,
    principal: Admin,
    sessions: Sessions,
    settings: AppSettings,
    rid: RequestId,
    filename: Annotated[str, Query(min_length=1, max_length=200, description="e.g. data.xlsx")],
    dry_run: bool = True,
    entity: Entity | None = None,
    date_order: Literal["dmy", "mdy"] | None = None,
    llm_mapping: Annotated[bool, Query(description="Map unknown headers with AI")] = False,
) -> ImportReport:
    declared = request.headers.get("content-length")
    if declared and declared.isdigit() and int(declared) > settings.import_max_bytes:
        raise ProblemError(413, "file-too-large", "Files up to 5 MB; split the workbook.")
    data = await request.body()
    if len(data) > settings.import_max_bytes:
        raise ProblemError(413, "file-too-large", "Files up to 5 MB; split the workbook.")
    if not data:
        raise ProblemError(422, "empty-file", "Send the file as the request body.")
    llm = _mapper(request, settings, llm_mapping)
    try:
        return await import_file(
            data,
            filename,
            tenant_id=principal.tenant_id,
            sessions=sessions,
            dry_run=dry_run,
            entity=entity,
            date_order=date_order,
            llm=llm,
            actor=actor_of(principal),
            request_id=rid,
        )
    except ImportFileError as exc:
        raise ProblemError(422, "unreadable-file", str(exc)) from None
