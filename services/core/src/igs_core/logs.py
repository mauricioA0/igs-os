"""Structured logging and request ids."""

import logging
import time
import uuid

import structlog
from starlette.types import ASGIApp, Message, Receive, Scope, Send

REQUEST_ID_HEADER = "x-request-id"


def configure_logging(level: str = "INFO", json: bool = False) -> None:
    renderer: structlog.types.Processor = (
        structlog.processors.JSONRenderer() if json else structlog.dev.ConsoleRenderer()
    )
    structlog.configure(
        processors=[
            structlog.contextvars.merge_contextvars,
            structlog.processors.add_log_level,
            structlog.processors.TimeStamper(fmt="iso", utc=True),
            structlog.processors.StackInfoRenderer(),
            structlog.processors.format_exc_info,
            renderer,
        ],
        wrapper_class=structlog.make_filtering_bound_logger(logging.getLevelName(level)),
        cache_logger_on_first_use=True,
    )


class RequestContextMiddleware:
    """Assigns a request id (or keeps the caller's), binds it to logs, echoes it back.

    Pure ASGI middleware so it also wraps streaming responses without buffering them.
    """

    def __init__(self, app: ASGIApp) -> None:
        self.app = app
        self.log = structlog.get_logger("igs_core.access")

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        headers = dict(scope["headers"])
        incoming = headers.get(REQUEST_ID_HEADER.encode(), b"").decode("latin-1")
        request_id = incoming if 0 < len(incoming) <= 128 else uuid.uuid4().hex
        scope.setdefault("state", {})["request_id"] = request_id

        structlog.contextvars.clear_contextvars()
        structlog.contextvars.bind_contextvars(
            request_id=request_id, method=scope["method"], path=scope["path"]
        )
        started = time.perf_counter()
        status = 500

        async def send_with_id(message: Message) -> None:
            nonlocal status
            if message["type"] == "http.response.start":
                status = message["status"]
                message.setdefault("headers", [])
                message["headers"].append((REQUEST_ID_HEADER.encode(), request_id.encode()))
            await send(message)

        try:
            await self.app(scope, receive, send_with_id)
        finally:
            self.log.info(
                "request",
                status=status,
                duration_ms=round((time.perf_counter() - started) * 1000, 1),
            )
