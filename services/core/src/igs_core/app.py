"""FastAPI application factory."""

import asyncio
import contextlib
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

import structlog
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from igs_core import db
from igs_core.agent import routes as copilot_routes
from igs_core.api import health, v1
from igs_core.api.v1 import accounts_ai, public_chat
from igs_core.config import Settings, get_settings
from igs_core.errors import PROBLEM_RESPONSES, install_error_handlers
from igs_core.events import CHANNEL_NODE_RUNS, CHANNEL_OUTBOX
from igs_core.events.dispatcher import OutboxDispatcher
from igs_core.events.listen import NotificationHub
from igs_core.guide import routes as guide_routes
from igs_core.logs import REQUEST_ID_HEADER, RequestContextMiddleware, configure_logging
from igs_core.mcp.service import install_mcp
from igs_core.repositories import Repositories
from igs_core.repositories.sql import SqlAccounts, SqlDirectory, SqlTrips
from igs_core.temporal import TemporalGateway, WorkflowGateway

log = structlog.get_logger("igs_core.app")


def create_app(
    settings: Settings | None = None,
    repos: Repositories | None = None,
    workflows: WorkflowGateway | None = None,
) -> FastAPI:
    """Build the API.

    - ``repos``: run without a database (tests, OpenAPI export); the write side answers 503.
    - ``workflows``: Temporal gateway override (tests use ``RecordingGateway``).
    """
    settings = settings or get_settings()
    configure_logging(settings.log_level, json=settings.log_json)
    gateway: WorkflowGateway = workflows or TemporalGateway(settings)

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        app.state.workflows = gateway
        if repos is not None:
            app.state.repos = repos
            yield
            return
        engine = db.open_engine(settings.database_url)
        await db.verify_rls(engine)  # fail closed at boot if RLS isn't actually enforced
        app.state.repos = Repositories(
            directory=SqlDirectory(engine),
            trips=SqlTrips(db.tenant_session),
            accounts=SqlAccounts(db.tenant_session),
        )
        app.state.tenant_session = db.tenant_session
        hub = NotificationHub(engine, (CHANNEL_NODE_RUNS, CHANNEL_OUTBOX))
        app.state.hub = hub
        dispatcher: OutboxDispatcher | None = None
        dispatcher_task: asyncio.Task[None] | None = None
        if settings.run_outbox_dispatcher:
            dispatcher = OutboxDispatcher(gateway, engine=engine)
            dispatcher_task = asyncio.create_task(dispatcher.run_forever(hub))
        try:
            yield
        finally:
            if dispatcher is not None and dispatcher_task is not None:
                dispatcher.stop()
                dispatcher_task.cancel()
                with contextlib.suppress(asyncio.CancelledError, Exception):
                    await dispatcher_task
            await hub.stop()
            await db.close_engine()

    app = FastAPI(
        title="IGS OS Core API",
        version="0.2.0",
        summary="Operations, flows and Account 360 for Infinity Global Sports (demo).",
        lifespan=lifespan,
        docs_url="/docs" if settings.environment != "production" else None,
        redoc_url=None,
    )
    app.state.settings = settings
    app.state.workflows = gateway
    if repos is not None:
        app.state.repos = repos

    install_error_handlers(app)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_origin_regex=settings.cors_origin_regex,
        allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE"],
        allow_headers=[
            "authorization",
            "content-type",
            "idempotency-key",
            "if-match",
            REQUEST_ID_HEADER,
        ],
        expose_headers=[REQUEST_ID_HEADER, "etag"],
        allow_credentials=False,
        max_age=600,
    )
    # Outermost, so every response (including CORS and errors) carries the request id.
    app.add_middleware(RequestContextMiddleware)

    app.include_router(health.router)
    app.include_router(v1.router)
    app.include_router(accounts_ai.router, prefix="/v1", responses=PROBLEM_RESPONSES)
    app.include_router(public_chat.router, prefix="/v1", responses=PROBLEM_RESPONSES)
    app.include_router(copilot_routes.router, responses=PROBLEM_RESPONSES)  # carries /v1/copilot
    app.include_router(guide_routes.router, responses=PROBLEM_RESPONSES)  # carries /v1/guide
    if settings.mcp_enabled:
        install_mcp(app)  # /mcp + OAuth metadata; runs the MCP session manager in the lifespan
    return app
