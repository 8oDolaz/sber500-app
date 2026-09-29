"""Analytics storage (ARCHITECTURE §9.3–9.5). Append-only, no FKs to product tables."""

import uuid
from datetime import date, datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import BigInteger, Date, DateTime, Integer, Numeric, PrimaryKeyConstraint, String, func
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from planner.infra.db import Base


class AnalyticsEventRow(Base):
    """Partitioned by month on `occurred_at` (partitions are managed by migration + periodic job)."""

    __tablename__ = "analytics_events"
    __table_args__ = (
        PrimaryKeyConstraint("id", "occurred_at"),
        {"postgresql_partition_by": "RANGE (occurred_at)"},
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True))
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    received_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    name: Mapped[str] = mapped_column(String(100), index=True)
    schema_version: Mapped[int] = mapped_column(Integer)
    source: Mapped[str] = mapped_column(String(10))  # server | client
    platform: Mapped[str] = mapped_column(String(32))
    user_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), index=True)
    family_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    anonymous_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), index=True)
    session_id: Mapped[str | None] = mapped_column(String(64))
    app_version: Mapped[str | None] = mapped_column(String(32))
    properties: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict)


class UserActivityDaily(Base):
    __tablename__ = "user_activity_daily"
    __table_args__ = (PrimaryKeyConstraint("user_id", "activity_date", "platform"),)

    user_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True))
    activity_date: Mapped[date] = mapped_column(Date)
    platform: Mapped[str] = mapped_column(String(32))
    family_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    first_seen_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class LlmUsage(Base):
    __tablename__ = "llm_usage"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True)
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    request_id: Mapped[str | None] = mapped_column(String(64))
    trace_id: Mapped[str | None] = mapped_column(String(64))
    conversation_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    user_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), index=True)
    family_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), index=True)
    feature: Mapped[str] = mapped_column(String(32))
    provider: Mapped[str] = mapped_column(String(32))
    model: Mapped[str] = mapped_column(String(100))
    input_tokens: Mapped[int] = mapped_column(Integer, default=0)
    output_tokens: Mapped[int] = mapped_column(Integer, default=0)
    cached_input_tokens: Mapped[int] = mapped_column(Integer, default=0)
    status: Mapped[str] = mapped_column(String(16))  # ok | error | timeout | budget_exceeded | fallback
    latency_ms: Mapped[int] = mapped_column(Integer)
    # Money as integer micro-units (1 RUB = 1_000_000), never float.
    cost_micros: Mapped[int | None] = mapped_column(BigInteger)
    currency: Mapped[str] = mapped_column(String(3), default="RUB")
    cost_source: Mapped[str] = mapped_column(String(16))  # proxy | price_table | unpriced
    price_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))


class ModelPrice(Base):
    """Versioned prices so historical costs never change (ARCHITECTURE §9.5)."""

    __tablename__ = "model_prices"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True)
    provider: Mapped[str] = mapped_column(String(32))
    model: Mapped[str] = mapped_column(String(100), index=True)
    currency: Mapped[str] = mapped_column(String(3), default="RUB")
    input_per_million: Mapped[Decimal] = mapped_column(Numeric(18, 6))
    output_per_million: Mapped[Decimal] = mapped_column(Numeric(18, 6))
    cached_input_per_million: Mapped[Decimal | None] = mapped_column(Numeric(18, 6))
    effective_from: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    effective_to: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    source: Mapped[str] = mapped_column(String(32))  # proxy_model_info | manual
