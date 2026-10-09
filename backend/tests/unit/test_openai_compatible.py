"""The adapter against a local stand-in for the LiteLLM proxy (real HTTP, no mocks of the SDK)."""

import threading
import time
from collections.abc import Iterator
from decimal import Decimal

import pytest
import uvicorn
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from planner.modules.assistant.llm_gateway.openai_compatible import OpenAICompatibleProvider
from planner.modules.assistant.llm_gateway.port import (
    ChatMessage,
    Image,
    LLMBudgetExceeded,
    LLMRateLimited,
    LLMRequest,
)

proxy = FastAPI()
state: dict = {}


@proxy.post("/v1/chat/completions")
async def chat(request: Request) -> JSONResponse:
    body = await request.json()
    state["last_body"] = body
    mode = state.get("mode", "ok")
    if mode == "budget":
        return JSONResponse(
            {
                "error": {
                    "message": "Budget has been exceeded! Current cost: 66.7, Max budget: 66.67",
                    "type": "budget_exceeded",
                    "code": "400",
                }
            },
            status_code=429,
        )
    if mode == "ratelimit":
        return JSONResponse({"error": {"message": "Too many requests", "type": "rate_limit"}}, status_code=429)
    return JSONResponse(
        {
            "id": "chatcmpl-1",
            "object": "chat.completion",
            "created": 0,
            "model": body["model"],
            "choices": [
                {"index": 0, "finish_reason": "stop", "message": {"role": "assistant", "content": '{"items": []}'}}
            ],
            "usage": {"prompt_tokens": 120, "completion_tokens": 8, "total_tokens": 128},
        },
        headers={"x-litellm-response-cost": "0.00321"},
    )


@proxy.get("/v1/models")
async def models() -> dict:
    return {
        "object": "list",
        "data": [{"id": "deepseek-v4.1-flash", "object": "model", "created": 0, "owned_by": "cloud.ru"}],
    }


@pytest.fixture(scope="module")
def proxy_url() -> Iterator[str]:
    server = uvicorn.Server(uvicorn.Config(proxy, host="127.0.0.1", port=0, log_level="warning"))
    thread = threading.Thread(target=server.run, daemon=True)
    thread.start()
    while not server.started:
        time.sleep(0.01)
    port = server.servers[0].sockets[0].getsockname()[1]
    yield f"http://127.0.0.1:{port}/v1"
    server.should_exit = True
    thread.join(5)


def provider(url: str) -> OpenAICompatibleProvider:
    return OpenAICompatibleProvider(base_url=url, api_key="accelerator-test", timeout_s=5)


REQ = LLMRequest(
    model="deepseek-v4.1-flash", messages=[ChatMessage("user", "забрать посылку до 26.09")], json_mode=True
)


async def test_completion_usage_and_proxy_cost(proxy_url: str) -> None:
    state["mode"] = "ok"
    result = await provider(proxy_url).complete(REQ)
    assert result.text == '{"items": []}'
    assert (result.input_tokens, result.output_tokens) == (120, 8)
    assert result.reported_cost == Decimal("0.00321")
    assert state["last_body"]["response_format"] == {"type": "json_object"}


async def test_images_are_sent_as_data_urls(proxy_url: str) -> None:
    state["mode"] = "ok"
    photo = ChatMessage("user", "что на фото?", images=(Image(b"\x89PNG", "image/png"),))
    await provider(proxy_url).complete(LLMRequest(model="qwen3-vl-30b-a3b-instruct", messages=[photo]))
    assert state["last_body"]["messages"] == [
        {
            "role": "user",
            "content": [
                {"type": "text", "text": "что на фото?"},
                {"type": "image_url", "image_url": {"url": "data:image/png;base64,iVBORw=="}},
            ],
        }
    ]


async def test_budget_429_maps_to_budget_exceeded(proxy_url: str) -> None:
    state["mode"] = "budget"
    with pytest.raises(LLMBudgetExceeded):
        await provider(proxy_url).complete(REQ)


async def test_plain_429_is_rate_limited(proxy_url: str) -> None:
    state["mode"] = "ratelimit"
    with pytest.raises(LLMRateLimited):
        await provider(proxy_url).complete(REQ)


async def test_list_models(proxy_url: str) -> None:
    assert await provider(proxy_url).list_models() == ["deepseek-v4.1-flash"]
