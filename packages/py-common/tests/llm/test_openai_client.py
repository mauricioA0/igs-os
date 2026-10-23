"""OpenAILLM against a mocked HTTP transport: real SDK, no network."""

import json
from collections.abc import Callable
from decimal import Decimal
from typing import Any

import httpx2
import pytest
from openai import AsyncOpenAI
from pydantic import BaseModel

from igs_common.llm import (
    AssistantTurn,
    Completed,
    LLMError,
    LLMSettings,
    Message,
    OpenAILLM,
    PriceTable,
    Role,
    TextDelta,
    ToolCallReady,
    ToolResult,
    ToolSpec,
)
from igs_common.llm.openai_client import to_input_items

MODEL = "test-model-1"


class Args(BaseModel):
    trip_id: str


class Brief(BaseModel):
    status: str


def _response(output: list[dict[str, Any]], *, status: str = "completed", **extra: Any) -> dict:
    return {
        "id": "resp_1",
        "object": "response",
        "created_at": 1,
        "model": MODEL,
        "status": status,
        "output": output,
        "parallel_tool_calls": True,
        "tool_choice": "auto",
        "tools": [],
        "usage": {
            "input_tokens": 1000,
            "input_tokens_details": {"cached_tokens": 400, "cache_write_tokens": 0},
            "output_tokens": 200,
            "output_tokens_details": {"reasoning_tokens": 50},
            "total_tokens": 1200,
        },
        **extra,
    }


def _message(text: str) -> dict:
    return {
        "type": "message",
        "id": "msg_1",
        "role": "assistant",
        "status": "completed",
        "content": [{"type": "output_text", "text": text, "annotations": []}],
    }


def _llm(handler: Callable[[httpx2.Request], httpx2.Response]) -> tuple[OpenAILLM, list[dict]]:
    bodies: list[dict] = []

    def capture(request: httpx2.Request) -> httpx2.Response:
        if request.content:
            bodies.append(json.loads(request.content))
        return handler(request)

    client = AsyncOpenAI(
        api_key="sk-test",
        base_url="https://api.test/v1",
        max_retries=0,
        http_client=httpx2.AsyncClient(transport=httpx2.MockTransport(capture)),
    )
    settings = LLMSettings(models={Role.AGENT: MODEL, Role.EXTRACTOR: MODEL})
    prices = PriceTable.from_dict(
        {"version": "t", "models": {MODEL: {"input": 2, "cached_input": 0.5, "output": 10}}}
    )
    return OpenAILLM(settings, client=client, prices=prices), bodies


async def test_tool_call_request_and_mapping() -> None:
    llm, bodies = _llm(
        lambda _: httpx2.Response(
            200,
            json=_response(
                [
                    {"type": "reasoning", "id": "rs_1", "summary": [], "encrypted_content": "enc"},
                    {
                        "type": "function_call",
                        "id": "fc_1",
                        "call_id": "call_1",
                        "name": "get_trip",
                        "arguments": '{"trip_id": "t-2711"}',
                        "status": "completed",
                    },
                ]
            ),
        )
    )
    tools = [ToolSpec("get_trip", "Get a trip.", Args)]
    result = await llm.generate(Role.AGENT, [Message("user", "status?")], tools=tools)

    body = bodies[0]
    assert body["model"] == MODEL
    assert body["store"] is False
    assert body["include"] == ["reasoning.encrypted_content"]
    assert body["tools"][0]["strict"] is True
    assert body["tools"][0]["parameters"]["additionalProperties"] is False
    assert body["parallel_tool_calls"] is True

    assert result.finish_reason == "tool_calls"
    assert result.tool_calls[0].arguments == {"trip_id": "t-2711"}
    assert result.usage.cached_input_tokens == 400
    assert result.usage.reasoning_tokens == 50
    # 600 uncached * 2 + 400 cached * 0.5 + 200 * 10 = 3400 per million
    assert result.cost_usd == Decimal("0.003400")


def test_replay_of_openai_turn_and_tool_results() -> None:
    turn = AssistantTurn(
        text="",
        provider="openai",
        provider_items=(
            {"type": "reasoning", "id": "rs_1", "summary": [], "encrypted_content": "enc"},
            {"type": "function_call", "call_id": "c1", "name": "get_trip", "arguments": "{}"},
        ),
    )
    items = to_input_items(
        [Message("user", "hi"), turn, ToolResult("c1", "not found", is_error=True)]
    )
    assert items[1]["type"] == "reasoning"
    assert items[2]["type"] == "function_call"
    assert items[3] == {
        "type": "function_call_output",
        "call_id": "c1",
        "output": "ERROR: not found",
    }


async def test_structured_output_parsed() -> None:
    llm, bodies = _llm(
        lambda _: httpx2.Response(200, json=_response([_message('{"status": "active"}')]))
    )
    result = await llm.generate(Role.EXTRACTOR, [Message("user", "brief")], output_model=Brief)
    assert result.parsed == Brief(status="active")
    fmt = bodies[0]["text"]["format"]
    assert fmt["type"] == "json_schema" and fmt["strict"] is True


async def test_incomplete_maps_to_length_and_failed_raises() -> None:
    llm, _ = _llm(
        lambda _: httpx2.Response(
            200,
            json=_response(
                [_message("partial")],
                status="incomplete",
                incomplete_details={"reason": "max_output_tokens"},
            ),
        )
    )
    assert (await llm.generate(Role.AGENT, [Message("user", "x")])).finish_reason == "length"

    failed, _ = _llm(
        lambda _: httpx2.Response(
            200,
            json=_response([], status="failed", error={"code": "server_error", "message": "boom"}),
        )
    )
    with pytest.raises(LLMError, match="boom"):
        await failed.generate(Role.AGENT, [Message("user", "x")])


async def test_http_errors_become_llm_errors() -> None:
    llm, _ = _llm(lambda _: httpx2.Response(429, json={"error": {"message": "slow down"}}))
    with pytest.raises(LLMError):
        await llm.generate(Role.AGENT, [Message("user", "x")])


async def test_unknown_role_is_a_config_error() -> None:
    llm, _ = _llm(lambda _: httpx2.Response(500))
    with pytest.raises(LLMError, match="no model configured"):
        await llm.generate(Role.JUDGE, [Message("user", "x")])


async def test_stream_text_and_tool_events() -> None:
    call = {
        "type": "function_call",
        "id": "fc_1",
        "call_id": "call_1",
        "name": "get_trip",
        "arguments": '{"trip_id": "t-1"}',
        "status": "completed",
    }
    events = [
        {
            "type": "response.output_text.delta",
            "item_id": "m",
            "output_index": 0,
            "content_index": 0,
            "delta": "Hola ",
            "logprobs": [],
            "sequence_number": 1,
        },
        {
            "type": "response.output_item.added",
            "output_index": 1,
            "item": {**call, "arguments": "", "status": "in_progress"},
            "sequence_number": 2,
        },
        {
            "type": "response.output_item.done",
            "output_index": 1,
            "item": call,
            "sequence_number": 3,
        },
        {
            "type": "response.completed",
            "sequence_number": 4,
            "response": _response([_message("Hola "), call]),
        },
    ]
    sse = "".join(f"event: {e['type']}\ndata: {json.dumps(e)}\n\n" for e in events)
    llm, _ = _llm(
        lambda _: httpx2.Response(
            200, content=sse.encode(), headers={"content-type": "text/event-stream"}
        )
    )
    seen = [e async for e in llm.stream(Role.AGENT, [Message("user", "x")])]

    assert isinstance(seen[0], TextDelta) and seen[0].delta == "Hola "
    assert any(
        isinstance(e, ToolCallReady) and e.call.arguments == {"trip_id": "t-1"} for e in seen
    )
    assert isinstance(seen[-1], Completed)
    assert seen[-1].result.finish_reason == "tool_calls"


async def test_list_available_models() -> None:
    llm, _ = _llm(
        lambda _: httpx2.Response(
            200,
            json={
                "object": "list",
                "data": [
                    {"id": "b-model", "object": "model", "created": 1, "owned_by": "x"},
                    {"id": "a-model", "object": "model", "created": 1, "owned_by": "x"},
                ],
            },
        )
    )
    assert await llm.list_available_models() == ["a-model", "b-model"]


def test_free_form_object_tools_are_sent_non_strict() -> None:
    # Strict mode 400s the whole request on `dict[str, Any]` fields (red team 2026-10: every
    # copilot turn failed because of run_flow_test.payload).
    from typing import Any

    from pydantic import BaseModel, ConfigDict

    from igs_common.llm.openai_client import to_function_tool
    from igs_common.llm.types import ToolSpec

    class Closed(BaseModel):
        model_config = ConfigDict(extra="forbid")
        name: str

    class Open(BaseModel):
        model_config = ConfigDict(extra="forbid")
        payload: dict[str, Any]

    assert to_function_tool(ToolSpec("closed", "d", Closed))["strict"] is True
    tool = to_function_tool(ToolSpec("open", "d", Open))
    assert tool["strict"] is False
    assert "payload" in tool["parameters"]["properties"]
