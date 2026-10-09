"""Transactional outbox (ARCHITECTURE §3, §10).

Side effects are written as rows in the same transaction as the domain change,
then delivered by `OutboxDispatcher` running in the worker.
"""

from collections.abc import Awaitable, Callable
from datetime import UTC, datetime
from typing import Any

import structlog
from sqlalchemy import BigInteger, DateTime, Index, Integer, String, Text, func, select, text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Mapped, mapped_column

from planner.infra.db import Base, Database
from planner.infra.ids import new_id
from planner.infra.telemetry import OUTBOX_DISPATCHED, OUTBOX_LAG

log = structlog.get_logger(__name__)

MAX_ATTEMPTS = 10

Handler = Callable[[AsyncSession, dict[str, Any]], Awaitable[None]]


class OutboxMessage(Base):
    __tablename__ = "outbox_messages"
    __table_args__ = (Index("ix_outbox_messages_pending", "seq", postgresql_where=text("dispatched_at IS NULL")),)

    seq: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    id: Mapped[Any] = mapped_column(UUID(as_uuid=True), unique=True, default=new_id)
    topic: Mapped[str] = mapped_column(String(100))
    payload: Mapped[dict[str, Any]] = mapped_column(JSONB)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    dispatched_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    attempts: Mapped[int] = mapped_column(Integer, default=0)
    last_error: Mapped[str | None] = mapped_column(Text)


def enqueue(session: AsyncSession, topic: str, payload: dict[str, Any]) -> None:
    """Add a message to the outbox inside the caller's transaction."""
    session.add(OutboxMessage(topic=topic, payload=payload))


class OutboxDispatcher:
    def __init__(self, db: Database) -> None:
        self._db = db
        self._handlers: dict[str, Handler] = {}

    def register(self, topic: str, handler: Handler) -> None:
        self._handlers[topic] = handler

    async def dispatch_batch(self, limit: int = 200) -> int:
        """Deliver up to `limit` pending messages. Safe to run concurrently (SKIP LOCKED)."""
        async with self._db.transaction() as session:
            rows = (
                await session.scalars(
                    select(OutboxMessage)
                    .where(OutboxMessage.dispatched_at.is_(None), OutboxMessage.attempts < MAX_ATTEMPTS)
                    .order_by(OutboxMessage.seq)
                    .limit(limit)
                    .with_for_update(skip_locked=True)
                )
            ).all()
            if rows:
                OUTBOX_LAG.set((datetime.now(UTC) - rows[0].created_at).total_seconds())
            else:
                OUTBOX_LAG.set(0)
            for msg in rows:
                handler = self._handlers.get(msg.topic)
                if handler is None:
                    msg.attempts = MAX_ATTEMPTS
                    msg.last_error = f"no handler for topic {msg.topic!r}"
                    OUTBOX_DISPATCHED.labels(topic=msg.topic, status="no_handler").inc()
                    continue
                try:
                    async with session.begin_nested():
                        await handler(session, msg.payload)
                except Exception as exc:  # noqa: BLE001 — one bad message must not block the batch
                    msg.attempts += 1
                    msg.last_error = repr(exc)[:2000]
                    OUTBOX_DISPATCHED.labels(topic=msg.topic, status="error").inc()
                    log.warning("outbox.handler_failed", topic=msg.topic, id=str(msg.id), error=repr(exc))
                else:
                    msg.dispatched_at = datetime.now(UTC)
                    OUTBOX_DISPATCHED.labels(topic=msg.topic, status="ok").inc()
            return len(rows)

    async def purge_dispatched(self, older_than_days: int = 7) -> None:
        async with self._db.transaction() as session:
            await session.execute(
                text("DELETE FROM outbox_messages WHERE dispatched_at < now() - make_interval(days => :d)"),
                {"d": older_than_days},
            )
