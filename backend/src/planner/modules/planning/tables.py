import uuid
from datetime import date, datetime

from sqlalchemy import Boolean, CheckConstraint, Date, DateTime, ForeignKey, Index, String, Text, func, text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from planner.infra.db import Base


class TaskRow(Base):
    __tablename__ = "tasks"
    __table_args__ = (Index("ix_tasks_family_open", "family_id", postgresql_where=text("status = 'open'")),)

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True)
    family_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("families.id", ondelete="CASCADE"), index=True)
    title: Mapped[str] = mapped_column(String(300))
    due_date: Mapped[date | None] = mapped_column(Date)
    due_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    assignee_hint: Mapped[str | None] = mapped_column(String(120))
    status: Mapped[str] = mapped_column(String(8), default="open")  # open | done
    created_by: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    created_via: Mapped[str] = mapped_column(String(16))
    # The message the task came from (shown on request; never sent to analytics).
    source_text: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    completed_by: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))


class EventRow(Base):
    __tablename__ = "events"
    __table_args__ = (
        CheckConstraint(
            "(all_day AND start_date IS NOT NULL AND starts_at IS NULL)"
            " OR (NOT all_day AND starts_at IS NOT NULL AND start_date IS NULL)",
            name="timed_or_all_day",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True)
    family_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("families.id", ondelete="CASCADE"), index=True)
    title: Mapped[str] = mapped_column(String(300))
    all_day: Mapped[bool] = mapped_column(Boolean)
    starts_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), index=True)
    ends_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    start_date: Mapped[date | None] = mapped_column(Date, index=True)
    timezone: Mapped[str] = mapped_column(String(64))  # the family's zone when created
    participants_hint: Mapped[str | None] = mapped_column(String(120))
    created_by: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    created_via: Mapped[str] = mapped_column(String(16))
    source_text: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
