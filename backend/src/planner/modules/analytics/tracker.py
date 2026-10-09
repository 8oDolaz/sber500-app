"""Server-side tracking and the analytics sink (ARCHITECTURE §9.2, §9.6)."""

import uuid
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any, Protocol

from pydantic import BaseModel
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from planner.infra.ids import new_id
from planner.infra.outbox import enqueue
from planner.infra.telemetry import ANALYTICS_INGESTED
from planner.modules.analytics.catalog import Platform, spec_for
from planner.modules.analytics.tables import AnalyticsEventRow

OUTBOX_TOPIC = "analytics.event"


@dataclass(frozen=True, slots=True)
class EventContext:
    """Who/where. Set by the server from the session or bot update, never trusted from clients."""

    platform: Platform
    user_id: uuid.UUID | None = None
    family_id: uuid.UUID | None = None
    anonymous_id: uuid.UUID | None = None
    session_id: str | None = None
    app_version: str | None = None


@dataclass(frozen=True, slots=True)
class AnalyticsRecord:
    id: uuid.UUID
    name: str
    schema_version: int
    source: str
    occurred_at: datetime
    platform: str
    user_id: uuid.UUID | None
    family_id: uuid.UUID | None
    anonymous_id: uuid.UUID | None
    session_id: str | None
    app_version: str | None
    properties: dict[str, Any]

    def to_payload(self) -> dict[str, Any]:
        return {
            "id": str(self.id),
            "name": self.name,
            "schema_version": self.schema_version,
            "source": self.source,
            "occurred_at": self.occurred_at.isoformat(),
            "platform": self.platform,
            "user_id": _s(self.user_id),
            "family_id": _s(self.family_id),
            "anonymous_id": _s(self.anonymous_id),
            "session_id": self.session_id,
            "app_version": self.app_version,
            "properties": self.properties,
        }

    @classmethod
    def from_payload(cls, p: dict[str, Any]) -> "AnalyticsRecord":
        return cls(
            id=uuid.UUID(p["id"]),
            name=p["name"],
            schema_version=p["schema_version"],
            source=p["source"],
            occurred_at=datetime.fromisoformat(p["occurred_at"]),
            platform=p["platform"],
            user_id=_u(p.get("user_id")),
            family_id=_u(p.get("family_id")),
            anonymous_id=_u(p.get("anonymous_id")),
            session_id=p.get("session_id"),
            app_version=p.get("app_version"),
            properties=p.get("properties") or {},
        )


def _s(v: uuid.UUID | None) -> str | None:
    return str(v) if v else None


def _u(v: str | None) -> uuid.UUID | None:
    return uuid.UUID(v) if v else None


class AnalyticsSink(Protocol):
    async def write(self, session: AsyncSession, records: list[AnalyticsRecord]) -> None: ...


class PostgresSink:
    async def write(self, session: AsyncSession, records: list[AnalyticsRecord]) -> None:
        if not records:
            return
        stmt = insert(AnalyticsEventRow).values(
            [
                {
                    "id": r.id,
                    "occurred_at": r.occurred_at,
                    "name": r.name,
                    "schema_version": r.schema_version,
                    "source": r.source,
                    "platform": r.platform,
                    "user_id": r.user_id,
                    "family_id": r.family_id,
                    "anonymous_id": r.anonymous_id,
                    "session_id": r.session_id,
                    "app_version": r.app_version,
                    "properties": r.properties,
                }
                for r in records
            ]
        )
        # id (+ occurred_at, the partition key) is the dedupe key: client retries are safe.
        await session.execute(stmt.on_conflict_do_nothing())
        for r in records:
            ANALYTICS_INGESTED.labels(source=r.source).inc()


class Tracker:
    """Emit server events through the outbox, in the caller's transaction."""

    def track(self, session: AsyncSession, event: BaseModel, ctx: EventContext) -> None:
        spec = spec_for(event)
        record = AnalyticsRecord(
            id=new_id(),
            name=spec.name,
            schema_version=spec.version,
            source="server",
            occurred_at=datetime.now(UTC),
            platform=ctx.platform.value,
            user_id=ctx.user_id,
            family_id=ctx.family_id,
            anonymous_id=ctx.anonymous_id,
            session_id=ctx.session_id,
            app_version=ctx.app_version,
            properties=event.model_dump(mode="json"),
        )
        enqueue(session, OUTBOX_TOPIC, record.to_payload())


def outbox_handler(sinks: list[AnalyticsSink]):
    async def handle(session: AsyncSession, payload: dict[str, Any]) -> None:
        record = AnalyticsRecord.from_payload(payload)
        for sink in sinks:
            await sink.write(session, [record])

    return handle
