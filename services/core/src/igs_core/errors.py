"""RFC 9457 problem details for every error the API returns."""

from http import HTTPStatus
from typing import Any

import structlog
from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from starlette.exceptions import HTTPException as StarletteHTTPException

PROBLEM_JSON = "application/problem+json"
PROBLEM_BASE = "https://igs-os.dev/problems/"


class Problem(BaseModel):
    type: str = "about:blank"
    title: str
    status: int
    detail: str | None = None
    instance: str | None = None
    request_id: str | None = None
    errors: list[dict[str, Any]] | None = None


class ProblemError(Exception):
    """Raise from handlers to return a typed problem (``type`` is a slug under PROBLEM_BASE)."""

    def __init__(
        self,
        status: int,
        slug: str,
        detail: str | None = None,
        headers: dict[str, str] | None = None,
        errors: list[dict[str, Any]] | None = None,
    ) -> None:
        self.status = status
        self.slug = slug
        self.detail = detail
        self.headers = headers or {}
        self.errors = errors
        super().__init__(detail or slug)


def problem_response(request: Request, problem: Problem) -> JSONResponse:
    problem.instance = problem.instance or request.url.path
    problem.request_id = getattr(request.state, "request_id", None)
    return JSONResponse(
        problem.model_dump(exclude_none=True), status_code=problem.status, media_type=PROBLEM_JSON
    )


def _title(status: int) -> str:
    try:
        return HTTPStatus(status).phrase
    except ValueError:
        return "Error"


def install_error_handlers(app: FastAPI) -> None:
    log = structlog.get_logger("igs_core.errors")

    @app.exception_handler(ProblemError)
    async def _problem(request: Request, exc: ProblemError) -> JSONResponse:
        response = problem_response(
            request,
            Problem(
                type=PROBLEM_BASE + exc.slug,
                title=_title(exc.status),
                status=exc.status,
                detail=exc.detail,
                errors=exc.errors,
            ),
        )
        response.headers.update(exc.headers)
        return response

    @app.exception_handler(StarletteHTTPException)
    async def _http(request: Request, exc: StarletteHTTPException) -> JSONResponse:
        response = problem_response(
            request,
            Problem(title=_title(exc.status_code), status=exc.status_code, detail=str(exc.detail)),
        )
        response.headers.update(exc.headers or {})
        return response

    @app.exception_handler(RequestValidationError)
    async def _validation(request: Request, exc: RequestValidationError) -> JSONResponse:
        errors = [
            {"loc": list(e.get("loc", ())), "msg": e.get("msg"), "type": e.get("type")}
            for e in exc.errors()
        ]
        return problem_response(
            request,
            Problem(
                type=PROBLEM_BASE + "validation-error",
                title="Unprocessable Content",
                status=422,
                detail="The request is not valid.",
                errors=errors,
            ),
        )

    @app.exception_handler(Exception)
    async def _unhandled(request: Request, exc: Exception) -> JSONResponse:
        log.exception("unhandled_error")
        return problem_response(
            request,
            Problem(title="Internal Server Error", status=500, detail="Unexpected error."),
        )


# OpenAPI: document problem+json on every route.
PROBLEM_RESPONSES: dict[int | str, dict[str, Any]] = {
    status: {"model": Problem, "content": {PROBLEM_JSON: {}}, "description": _title(status)}
    for status in (400, 401, 403, 404, 409, 412, 422, 428, 500, 502, 503)
}
