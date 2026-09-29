"""Daily activity for DAU/WAU/MAU (ARCHITECTURE §9.4, ADR docs/adr/0003-active-user.md).

One DB write per user per day per platform: Redis `SET NX` dedupes, the table
insert is idempotent anyway, so a Redis outage only costs extra writes.
"""

import uuid
from datetime import UTC, datetime
from zoneinfo import ZoneInfo

import structlog
from redis.asyncio import Redis
from sqlalchemy.dialects.postgresql import insert

from planner.infra.db import Database
from planner.modules.analytics.catalog import Platform
from planner.modules.analytics.tables import UserActivityDaily

log = structlog.get_logger(__name__)

# Not user-initiated or not meaningful activity (see ADR 0003).
EXCLUDED_API_PATHS = frozenset({"/v1/analytics/events", "/v1/auth/refresh", "/healthz", "/readyz", "/metrics"})


class ActivityRecorder:
    def __init__(self, db: Database, redis: Redis, reporting_tz: str) -> None:
        self._db = db
        self._redis = redis
        self._tz = ZoneInfo(reporting_tz)

    async def record(self, user_id: uuid.UUID, platform: Platform, family_id: uuid.UUID | None = None) -> None:
        """Failure-tolerant: analytics never breaks the product."""
        try:
            now = datetime.now(UTC)
            day = now.astimezone(self._tz).date()
            try:
                first = await self._redis.set(f"active:{day}:{user_id}:{platform.value}", 1, nx=True, ex=2 * 86400)
            except Exception:  # noqa: BLE001
                first = True
            if not first:
                return
            async with self._db.transaction() as session:
                await session.execute(
                    insert(UserActivityDaily)
                    .values(
                        user_id=user_id,
                        activity_date=day,
                        platform=platform.value,
                        family_id=family_id,
                        first_seen_at=now,
                    )
                    .on_conflict_do_nothing()
                )
        except Exception as exc:  # noqa: BLE001
            log.warning("activity.record_failed", error=repr(exc))
