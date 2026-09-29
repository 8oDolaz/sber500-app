"""`llm_usage` ledger, price book, quotas and spend monitoring (ARCHITECTURE §9.5, §6.5).

Cost source priority:
1. `proxy`       — cost reported by the accelerator LiteLLM proxy (what the budget is charged).
2. `price_table` — computed from versioned `model_prices`.
3. `unpriced`    — neither available; `cost_micros` stays NULL and shows up in reconciliation.
"""

import time
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import ROUND_HALF_UP, Decimal
from zoneinfo import ZoneInfo

import structlog
from redis.asyncio import Redis
from sqlalchemy import func, or_, select

from planner.infra.db import Database
from planner.infra.ids import new_id
from planner.infra.telemetry import LLM_LEDGER_WRITE_FAILED, LLM_SPEND_RUB
from planner.modules.analytics.tables import LlmUsage, ModelPrice

log = structlog.get_logger(__name__)

MICROS = Decimal(1_000_000)


def rub_to_micros(rub: Decimal) -> int:
    return int((rub * MICROS).quantize(Decimal(1), rounding=ROUND_HALF_UP))


@dataclass(frozen=True, slots=True)
class UsageEntry:
    feature: str
    provider: str
    model: str
    status: str
    latency_ms: int
    input_tokens: int = 0
    output_tokens: int = 0
    cached_input_tokens: int = 0
    reported_cost_rub: Decimal | None = None
    user_id: uuid.UUID | None = None
    family_id: uuid.UUID | None = None
    conversation_id: uuid.UUID | None = None
    request_id: str | None = None
    trace_id: str | None = None


@dataclass(frozen=True, slots=True)
class Priced:
    cost_micros: int | None
    source: str
    price_id: uuid.UUID | None


class PriceBook:
    def __init__(self, db: Database, ttl_s: float = 300) -> None:
        self._db = db
        self._ttl = ttl_s
        self._cache: dict[str, tuple[float, ModelPrice | None]] = {}

    async def current(self, model: str) -> ModelPrice | None:
        hit = self._cache.get(model)
        if hit and time.monotonic() - hit[0] < self._ttl:
            return hit[1]
        now = datetime.now(UTC)
        async with self._db.sessions() as session:
            price = await session.scalar(
                select(ModelPrice)
                .where(
                    ModelPrice.model == model,
                    ModelPrice.effective_from <= now,
                    or_(ModelPrice.effective_to.is_(None), ModelPrice.effective_to > now),
                )
                .order_by(ModelPrice.effective_from.desc())
                .limit(1)
            )
        self._cache[model] = (time.monotonic(), price)
        return price

    async def price(self, entry: UsageEntry) -> Priced:
        if entry.reported_cost_rub is not None:
            return Priced(rub_to_micros(entry.reported_cost_rub), "proxy", None)
        p = await self.current(entry.model)
        if p is None:
            return Priced(None, "unpriced", None)
        cached_rate = p.cached_input_per_million if p.cached_input_per_million is not None else p.input_per_million
        uncached = max(entry.input_tokens - entry.cached_input_tokens, 0)
        # tokens × (RUB per 1M tokens) = micro-RUB
        micros = (
            uncached * p.input_per_million
            + entry.cached_input_tokens * cached_rate
            + entry.output_tokens * p.output_per_million
        )
        return Priced(int(micros.quantize(Decimal(1), rounding=ROUND_HALF_UP)), "price_table", p.id)


class FamilyQuota:
    """Per-family daily spend cap, cached in Redis (rebuildable from the ledger)."""

    def __init__(self, redis: Redis, daily_limit_rub: Decimal, tz: str) -> None:
        self._redis = redis
        self._limit = rub_to_micros(daily_limit_rub)
        self._tz = ZoneInfo(tz)

    def _key(self, family_id: uuid.UUID) -> str:
        return f"llm:spent:{datetime.now(UTC).astimezone(self._tz).date()}:{family_id}"

    async def exceeded(self, family_id: uuid.UUID) -> bool:
        try:
            spent = await self._redis.get(self._key(family_id))
        except Exception:  # noqa: BLE001 — fail open; the program budget is still guarded by the proxy
            return False
        return spent is not None and int(spent) >= self._limit

    async def add(self, family_id: uuid.UUID, micros: int) -> None:
        try:
            key = self._key(family_id)
            await self._redis.incrby(key, micros)
            await self._redis.expire(key, 2 * 86400)
        except Exception as exc:  # noqa: BLE001
            log.warning("llm.quota_update_failed", error=repr(exc))


class LlmLedger:
    def __init__(self, db: Database, prices: PriceBook, quota: FamilyQuota | None = None) -> None:
        self._db = db
        self._prices = prices
        self._quota = quota

    async def record(self, entry: UsageEntry) -> None:
        """Written in its own transaction: quotas and cost reporting depend on it."""
        priced = await self._prices.price(entry)
        row = LlmUsage(
            id=new_id(),
            occurred_at=datetime.now(UTC),
            request_id=entry.request_id,
            trace_id=entry.trace_id,
            conversation_id=entry.conversation_id,
            user_id=entry.user_id,
            family_id=entry.family_id,
            feature=entry.feature,
            provider=entry.provider,
            model=entry.model,
            input_tokens=entry.input_tokens,
            output_tokens=entry.output_tokens,
            cached_input_tokens=entry.cached_input_tokens,
            status=entry.status,
            latency_ms=entry.latency_ms,
            cost_micros=priced.cost_micros,
            currency="RUB",
            cost_source=priced.source,
            price_id=priced.price_id,
        )
        for attempt in (1, 2):
            try:
                async with self._db.transaction() as session:
                    session.add(row)
                break
            except Exception as exc:  # noqa: BLE001
                LLM_LEDGER_WRITE_FAILED.inc()
                log.error("llm.ledger_write_failed", attempt=attempt, error=repr(exc))
        if self._quota and entry.family_id and priced.cost_micros:
            await self._quota.add(entry.family_id, priced.cost_micros)


class SpendMonitor:
    """Program-level budget alerts (Sber500: 50k ₽ first 2 weeks, ≤75k ₽ total)."""

    def __init__(self, db: Database, redis: Redis, budget_rub: int, thresholds: list[float]) -> None:
        self._db = db
        self._redis = redis
        self._budget = budget_rub
        self._thresholds = sorted(thresholds)

    async def check(self) -> Decimal:
        async with self._db.sessions() as session:
            micros = await session.scalar(
                select(func.coalesce(func.sum(LlmUsage.cost_micros), 0)).where(LlmUsage.provider != "fake")
            )
        spent = Decimal(int(micros or 0)) / MICROS
        LLM_SPEND_RUB.set(float(spent))
        for t in self._thresholds:
            if spent >= Decimal(str(t)) * self._budget:
                first = await self._redis.set(f"llm:budget_alert:{self._budget}:{t}", 1, nx=True)
                if first:
                    log.error(
                        "llm.budget_threshold_crossed", threshold=t, spent_rub=str(spent), budget_rub=self._budget
                    )
                    _sentry_message(f"LLM spend {spent} ₽ crossed {int(t * 100)}% of {self._budget} ₽ budget")
        return spent


def _sentry_message(msg: str) -> None:
    try:
        import sentry_sdk

        sentry_sdk.capture_message(msg, level="error")
    except Exception:  # noqa: BLE001
        pass
