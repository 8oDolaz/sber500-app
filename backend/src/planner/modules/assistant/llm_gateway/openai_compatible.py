"""Adapter for OpenAI-compatible endpoints — here the Sber500 accelerator LiteLLM proxy
in front of Cloud.ru Foundation Models (GigaChat, DeepSeek, …)."""

from decimal import Decimal, InvalidOperation

import openai
from openai import AsyncOpenAI

from planner.modules.assistant.llm_gateway.port import (
    LLMBudgetExceeded,
    LLMError,
    LLMRateLimited,
    LLMRequest,
    LLMResult,
    LLMTimeout,
)

COST_HEADER = "x-litellm-response-cost"


class OpenAICompatibleProvider:
    name = "accelerator"

    def __init__(self, *, base_url: str, api_key: str, timeout_s: float):
        # Retries are the gateway's decision (a budget 429 must never be retried).
        self._client = AsyncOpenAI(base_url=base_url, api_key=api_key, timeout=timeout_s, max_retries=0)

    async def complete(self, request: LLMRequest) -> LLMResult:
        kwargs: dict = {
            "model": request.model,
            "messages": [{"role": m.role, "content": m.content} for m in request.messages],
            "temperature": request.temperature,
        }
        if request.max_tokens is not None:
            kwargs["max_tokens"] = request.max_tokens
        if request.json_mode:
            kwargs["response_format"] = {"type": "json_object"}
        try:
            raw = await self._client.chat.completions.with_raw_response.create(**kwargs)
        except openai.APITimeoutError as exc:
            raise LLMTimeout(str(exc)) from exc
        except openai.RateLimitError as exc:
            if "budget" in str(exc).lower():
                raise LLMBudgetExceeded(str(exc)) from exc
            raise LLMRateLimited(str(exc)) from exc
        except openai.APIError as exc:
            raise LLMError(str(exc)) from exc

        completion = raw.parse()
        usage = completion.usage
        cached = 0
        if usage is not None and usage.prompt_tokens_details is not None:
            cached = usage.prompt_tokens_details.cached_tokens or 0
        return LLMResult(
            text=completion.choices[0].message.content or "",
            provider=self.name,
            model=completion.model or request.model,
            input_tokens=usage.prompt_tokens if usage else 0,
            output_tokens=usage.completion_tokens if usage else 0,
            cached_input_tokens=cached,
            reported_cost=_parse_cost(raw.headers.get(COST_HEADER)),
        )

    async def list_models(self) -> list[str]:
        try:
            page = await self._client.models.list()
        except openai.APIError as exc:
            raise LLMError(str(exc)) from exc
        return [m.id for m in page.data]


def _parse_cost(value: str | None) -> Decimal | None:
    if not value:
        return None
    try:
        cost = Decimal(value)
    except InvalidOperation:
        return None
    return cost if cost >= 0 else None
