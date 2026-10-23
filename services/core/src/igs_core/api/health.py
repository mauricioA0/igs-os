import asyncio

from fastapi import APIRouter
from fastapi.responses import JSONResponse

from igs_core.deps import Repos

router = APIRouter(tags=["health"])

READY_TIMEOUT_S = 2.0


@router.get("/healthz", summary="Liveness")
async def healthz() -> dict[str, str]:
    return {"status": "ok"}


@router.get("/readyz", summary="Readiness (database reachable)")
async def readyz(repos: Repos) -> JSONResponse:
    checks: dict[str, str] = {}
    try:
        await asyncio.wait_for(repos.directory.ping(), READY_TIMEOUT_S)
        checks["database"] = "ok"
    except Exception as exc:  # noqa: BLE001 — readiness reports, never raises
        checks["database"] = f"error: {type(exc).__name__}"
    ready = all(v == "ok" for v in checks.values())
    return JSONResponse(
        {"status": "ok" if ready else "unavailable", "checks": checks},
        status_code=200 if ready else 503,
    )
