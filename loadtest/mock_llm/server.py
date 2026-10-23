"""OpenAI-compatible mock (Responses + Models API) so load tests never make paid calls.

Only what ``igs_common.llm.openai_client`` uses: ``POST /v1/responses`` (plain and
``stream: true``) and ``GET /v1/models``. Answers are short Spanish text with a fixed token
count; ``MOCK_LATENCY_MS`` (default 400) simulates time-to-first-token and
``MOCK_TOKEN_DELAY_MS`` (default 15) the gap between streamed chunks, so the API's own
overhead can be separated from model time.

    uv run --with fastapi --with uvicorn uvicorn loadtest.mock_llm.server:app --port 8099
"""

import asyncio
import json
import os
import time
import uuid
from collections.abc import AsyncIterator
from typing import Any

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse, StreamingResponse

LATENCY = int(os.environ.get("MOCK_LATENCY_MS", "400")) / 1000
TOKEN_DELAY = int(os.environ.get("MOCK_TOKEN_DELAY_MS", "15")) / 1000
ANSWER = (
    "Lakeshore está en rojo: la seña de reserva sigue vencida y el hotel libera el bloqueo "
    "de marzo el 31/10. Falta que Robert Haines apruebe el presupuesto."
)
CHUNKS = ANSWER.split(" ")

app = FastAPI(title="mock-openai")


def _response(model: str, text: str, status: str = "completed") -> dict[str, Any]:
    return {
        "id": f"resp_{uuid.uuid4().hex}",
        "object": "response",
        "created_at": int(time.time()),
        "model": model,
        "status": status,
        "output": [
            {
                "type": "message",
                "id": f"msg_{uuid.uuid4().hex}",
                "role": "assistant",
                "status": "completed",
                "content": [{"type": "output_text", "text": text, "annotations": []}],
            }
        ]
        if text
        else [],
        "usage": {
            "input_tokens": 1200,
            "input_tokens_details": {"cached_tokens": 800},
            "output_tokens": 60,
            "output_tokens_details": {"reasoning_tokens": 0},
            "total_tokens": 1260,
        },
        "parallel_tool_calls": True,
        "tool_choice": "auto",
        "tools": [],
    }


def _sse(event: dict[str, Any]) -> bytes:
    return f"event: {event['type']}\ndata: {json.dumps(event)}\n\n".encode()


async def _stream(model: str) -> AsyncIterator[bytes]:
    seq = 0
    created = _response(model, "", status="in_progress")
    yield _sse({"type": "response.created", "sequence_number": seq, "response": created})
    await asyncio.sleep(LATENCY)
    item_id = f"msg_{uuid.uuid4().hex}"
    for i, word in enumerate(CHUNKS):
        seq += 1
        yield _sse(
            {
                "type": "response.output_text.delta",
                "sequence_number": seq,
                "item_id": item_id,
                "output_index": 0,
                "content_index": 0,
                "delta": word if i == 0 else f" {word}",
                "logprobs": [],
            }
        )
        await asyncio.sleep(TOKEN_DELAY)
    seq += 1
    yield _sse(
        {"type": "response.completed", "sequence_number": seq, "response": _response(model, ANSWER)}
    )


@app.post("/v1/responses")
async def responses(request: Request) -> Any:
    body = await request.json()
    model = body.get("model", "mock")
    if body.get("stream"):
        return StreamingResponse(_stream(model), media_type="text/event-stream")
    await asyncio.sleep(LATENCY)
    return JSONResponse(_response(model, ANSWER))


@app.get("/v1/models")
async def models() -> dict[str, Any]:
    ids = ["gpt-6.1-sol", "gpt-6-luna", "gpt-6-astra"]
    return {
        "object": "list",
        "data": [{"id": i, "object": "model", "owned_by": "mock"} for i in ids],
    }


@app.get("/healthz")
async def healthz() -> dict[str, str]:
    return {"status": "ok"}
