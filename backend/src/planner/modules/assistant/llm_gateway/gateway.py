"""LLMGateway: the only way product code talks to a model.

Adds per-family quota checks, one retry on transient errors, metrics and a ledger row
for every provider call (ARCHITECTURE §6.1 principle 5).
"""

import time
import uuid

import structlog

from planner.infra.telemetry import LLM_CALLS, LLM_LATENCY
from planner.modules.analytics.llm_ledger import FamilyQuota, LlmLedger, UsageEntry
from planner.modules.assistant.llm_gateway.port import (
    LLMBudgetExceeded,
    LLMError,
    LLMProvider,
    LLMQuotaExceeded,
    LLMRateLimited,
    LLMRequest,
    LLMResult,
    LLMTimeout,
)

log = structlog.get_logger(__name__)

RETRYABLE = (LLMTimeout, LLMRateLimited)


class LLMGateway:
    def __init__(
        self,
        provider: LLMProvider,
        ledger: LlmLedger,
        *,
        quota: FamilyQuota | None = None,
        on_budget_exceeded=None,
    ) -> None:
        self._provider = provider
        self._ledger = ledger
        self._quota = quota
        self._on_budget_exceeded = on_budget_exceeded

    @property
    def provider_name(self) -> str:
        return self._provider.name

    async def complete(
        self,
        request: LLMRequest,
        *,
        feature: str,
        user_id: uuid.UUID | None = None,
        family_id: uuid.UUID | None = None,
        conversation_id: uuid.UUID | None = None,
        request_id: str | None = None,
    ) -> LLMResult:
        if self._quota and family_id and await self._quota.exceeded(family_id):
            LLM_CALLS.labels(self._provider.name, request.model, feature, "quota_exceeded").inc()
            raise LLMQuotaExceeded(f"family {family_id} is over its daily LLM quota")

        last_exc: LLMError | None = None
        for attempt in (1, 2):
            started = time.perf_counter()
            try:
                result = await self._provider.complete(request)
            except LLMError as exc:
                latency_ms = int((time.perf_counter() - started) * 1000)
                await self._meter(
                    request, feature, exc.status, latency_ms, None, user_id, family_id, conversation_id, request_id
                )
                if isinstance(exc, LLMBudgetExceeded):
                    log.error("llm.budget_exceeded", model=request.model, feature=feature)
                    if self._on_budget_exceeded:
                        await self._on_budget_exceeded(request.model, feature)
                    raise
                last_exc = exc
                if attempt == 1 and isinstance(exc, RETRYABLE):
                    continue
                raise
            latency_ms = int((time.perf_counter() - started) * 1000)
            await self._meter(
                request, feature, "ok", latency_ms, result, user_id, family_id, conversation_id, request_id
            )
            return result
        assert last_exc is not None  # unreachable: loop either returns or raises
        raise last_exc

    async def list_models(self) -> list[str]:
        return await self._provider.list_models()

    async def _meter(
        self, request, feature, status, latency_ms, result, user_id, family_id, conversation_id, request_id
    ) -> None:
        LLM_CALLS.labels(self._provider.name, request.model, feature, status).inc()
        LLM_LATENCY.labels(self._provider.name, request.model).observe(latency_ms / 1000)
        await self._ledger.record(
            UsageEntry(
                feature=feature,
                provider=self._provider.name,
                model=result.model if result else request.model,
                status=status,
                latency_ms=latency_ms,
                input_tokens=result.input_tokens if result else 0,
                output_tokens=result.output_tokens if result else 0,
                cached_input_tokens=result.cached_input_tokens if result else 0,
                reported_cost_rub=result.reported_cost if result else None,
                user_id=user_id,
                family_id=family_id,
                conversation_id=conversation_id,
                request_id=request_id,
            )
        )
