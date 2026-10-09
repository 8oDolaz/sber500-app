import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import DateTime, ForeignKey, Index, String, Text, func, text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from planner.infra.db import Base


class DraftActionRow(Base):
    """A proposed write waiting for the user's confirmation (ARCHITECTURE §6.4)."""

    __tablename__ = "draft_actions"
    __table_args__ = (Index("ix_draft_actions_pending", "expires_at", postgresql_where=text("status = 'pending'")),)

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True)
    family_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("families.id", ondelete="CASCADE"), index=True)
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    command: Mapped[str] = mapped_column(String(32))  # create_task | create_event
    payload: Mapped[dict[str, Any]] = mapped_column(JSONB)
    summary: Mapped[str] = mapped_column(String(400))
    source: Mapped[str] = mapped_column(String(16))  # forwarded | own
    source_text: Mapped[str] = mapped_column(Text)
    model: Mapped[str | None] = mapped_column(String(100))  # None: saved as-is without the LLM
    status: Mapped[str] = mapped_column(String(16))  # pending | confirmed | cancelled | revised | expired
    revision_of: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    result_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))  # the created task/event
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
