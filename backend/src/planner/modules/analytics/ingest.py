"""Client event ingest (`POST /v1/analytics/events`)."""

import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

from pydantic import BaseModel, Field, ValidationError
from redis.asyncio import Redis

from planner.application.principal import Principal
from planner.infra.db import Database
from planner.infra.telemetry import ANALYTICS_REJECTED
from planner.modules.analytics.catalog import CATALOG, DisplayMode, Platform
from planner.modules.analytics.tracker import AnalyticsRecord, AnalyticsSink

MAX_FUTURE_SKEW = timedelta(minutes=5)
MAX_PAST_AGE = timedelta(days=7)


class ClientEvent(BaseModel):
    id: uuid.UUID
    name: str = Field(max_length=100)
    occurred_at: datetime
    properties: dict[str, Any] = Field(default_factory=dict)


class IngestBatch(BaseModel):
    anonymous_id: uuid.UUID
    session_id: str | None = Field(default=None, max_length=64)
    app_version: str | None = Field(default=None, max_length=32)
    events: list[ClientEvent] = Field(max_length=100)


class Rejection(BaseModel):
    id: uuid.UUID
    reason: str


class IngestResult(BaseModel):
    accepted: int
    rejected: list[Rejection]


class RateLimited(Exception):
    pass


class IngestService:
    def __init__(self, db: Database, redis: Redis, sinks: list[AnalyticsSink], preauth_rate_per_min: int) -> None:
        self._db = db
        self._redis = redis
        self._sinks = sinks
        self._rate = preauth_rate_per_min

    async def ingest(
        self,
        batch: IngestBatch,
        *,
        platform: Platform,
        display_mode: DisplayMode | None,
        principal: Principal | None,
        client_ip: str,
    ) -> IngestResult:
        if principal is None:
            await self._check_rate(f"ip:{client_ip}", len(batch.events))
            await self._check_rate(f"anon:{batch.anonymous_id}", len(batch.events))

        now = datetime.now(UTC)
        records: list[AnalyticsRecord] = []
        rejected: list[Rejection] = []
        for ev in batch.events:
            reason = self._validate(ev, principal)
            if reason:
                ANALYTICS_REJECTED.labels(reason=reason).inc()
                rejected.append(Rejection(id=ev.id, reason=reason))
                continue
            spec = CATALOG[ev.name]
            props = spec.model.model_validate(ev.properties).model_dump(mode="json")
            if display_mode is not None:
                props["display_mode"] = display_mode.value  # auto-property
            occurred = ev.occurred_at if now - MAX_PAST_AGE <= ev.occurred_at <= now + MAX_FUTURE_SKEW else now
            records.append(
                AnalyticsRecord(
                    id=ev.id,
                    name=spec.name,
                    schema_version=spec.version,
                    source="client",
                    occurred_at=occurred,
                    platform=platform.value,
                    user_id=principal.user_id if principal else None,
                    family_id=principal.family_id if principal else None,
                    anonymous_id=batch.anonymous_id,
                    session_id=batch.session_id,
                    app_version=batch.app_version,
                    properties=props,
                )
            )
        if records:
            async with self._db.transaction() as session:
                for sink in self._sinks:
                    await sink.write(session, records)
        return IngestResult(accepted=len(records), rejected=rejected)

    @staticmethod
    def _validate(ev: ClientEvent, principal: Principal | None) -> str | None:
        spec = CATALOG.get(ev.name)
        if spec is None:
            return "unknown_event"
        if spec.source != "client":
            return "server_only_event"
        if principal is None and not spec.preauth_allowed:
            return "auth_required"
        if ev.occurred_at.tzinfo is None:
            return "naive_timestamp"
        try:
            spec.model.model_validate(ev.properties)
        except ValidationError:
            return "invalid_properties"
        return None

    async def _check_rate(self, key: str, n: int) -> None:
        bucket = f"analytics:rate:{key}:{datetime.now(UTC):%Y%m%d%H%M}"
        count = await self._redis.incrby(bucket, n)
        if count == n:
            await self._redis.expire(bucket, 120)
        if count > self._rate:
            ANALYTICS_REJECTED.labels(reason="rate_limited").inc(n)
            raise RateLimited
