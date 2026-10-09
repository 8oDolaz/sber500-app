"""Planning commands and queries: the same calls serve the UI, the bot and the assistant (ARCHITECTURE §3)."""

import uuid
from dataclasses import dataclass
from datetime import UTC, date, datetime
from zoneinfo import ZoneInfo

from sqlalchemy import and_, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from planner.domain.planning import CreatedVia, NewEvent, NewTask, upcoming_window
from planner.infra.db import Database
from planner.infra.ids import new_id
from planner.modules.analytics.catalog import EventCreated, Platform, TaskCompleted, TaskCreated
from planner.modules.analytics.tracker import EventContext, Tracker
from planner.modules.families.tables import FamilyRow
from planner.modules.planning.tables import EventRow, TaskRow

OPEN_TASKS_LIMIT = 100
EVENTS_LIMIT = 100


@dataclass(frozen=True, slots=True)
class Actor:
    user_id: uuid.UUID | None
    family_id: uuid.UUID
    platform: Platform


class PlanningService:
    def __init__(self, db: Database, tracker: Tracker, app_version: str) -> None:
        self._db = db
        self._tracker = tracker
        self._app_version = app_version

    async def family_timezone(self, session: AsyncSession, family_id: uuid.UUID) -> str:
        tz = await session.scalar(select(FamilyRow.timezone).where(FamilyRow.id == family_id))
        return tz or "Europe/Moscow"

    async def create_task(
        self, session: AsyncSession, actor: Actor, task: NewTask, via: CreatedVia, source_text: str | None = None
    ) -> TaskRow:
        row = TaskRow(
            id=new_id(),
            family_id=actor.family_id,
            title=task.title,
            due_date=task.due_date,
            due_at=task.due_at,
            assignee_hint=task.assignee_hint,
            status="open",
            created_by=actor.user_id,
            created_via=via.value,
            source_text=source_text,
        )
        session.add(row)
        self._tracker.track(
            session,
            TaskCreated(
                task_id=row.id,
                created_via=via.value,
                has_due=task.due_date is not None,
                has_assignee=task.assignee_hint is not None,
            ),
            self._ctx(actor),
        )
        return row

    async def create_event(
        self, session: AsyncSession, actor: Actor, event: NewEvent, via: CreatedVia, source_text: str | None = None
    ) -> EventRow:
        row = EventRow(
            id=new_id(),
            family_id=actor.family_id,
            title=event.title,
            all_day=event.all_day,
            starts_at=event.starts_at,
            ends_at=event.ends_at,
            start_date=event.start_date,
            timezone=await self.family_timezone(session, actor.family_id),
            participants_hint=event.participants_hint,
            created_by=actor.user_id,
            created_via=via.value,
            source_text=source_text,
        )
        session.add(row)
        self._tracker.track(
            session, EventCreated(event_id=row.id, created_via=via.value, all_day=event.all_day), self._ctx(actor)
        )
        return row

    async def set_task_done(self, actor: Actor, task_id: uuid.UUID, done: bool) -> TaskRow | None:
        """Tap on the list dot. None when the task isn't in the actor's family."""
        async with self._db.transaction() as session:
            task = await session.scalar(
                select(TaskRow).where(TaskRow.id == task_id, TaskRow.family_id == actor.family_id).with_for_update()
            )
            if task is None:
                return None
            if done and task.status != "done":
                task.status, task.completed_at, task.completed_by = "done", datetime.now(UTC), actor.user_id
                self._tracker.track(
                    session,
                    TaskCompleted(task_id=task.id, created_via=task.created_via),  # type: ignore[arg-type]
                    self._ctx(actor),
                )
            elif not done and task.status != "open":
                task.status, task.completed_at, task.completed_by = "open", None, None
            return task

    async def open_tasks(self, family_id: uuid.UUID) -> list[TaskRow]:
        async with self._db.sessions() as session:
            rows = await session.scalars(
                select(TaskRow)
                .where(TaskRow.family_id == family_id, TaskRow.status == "open")
                .order_by(TaskRow.due_date.asc().nulls_last(), TaskRow.due_at.asc().nulls_last(), TaskRow.created_at)
                .limit(OPEN_TASKS_LIMIT)
            )
            return list(rows.all())

    async def upcoming_events(
        self, family_id: uuid.UUID, days: int = 7, now: datetime | None = None
    ) -> tuple[str, list[EventRow]]:
        """Events from the start of today (family timezone) for `days` days. Returns (timezone, events)."""
        async with self._db.sessions() as session:
            tz_name = await self.family_timezone(session, family_id)
            tz = ZoneInfo(tz_name)
            today = (now or datetime.now(UTC)).astimezone(tz).date()
            first, end = upcoming_window(today, days)
            start_utc = _midnight(first, tz)
            end_utc = _midnight(end, tz)
            rows = await session.scalars(
                select(EventRow)
                .where(
                    EventRow.family_id == family_id,
                    or_(
                        and_(
                            EventRow.all_day.is_(False), EventRow.starts_at >= start_utc, EventRow.starts_at < end_utc
                        ),
                        and_(EventRow.all_day.is_(True), EventRow.start_date >= first, EventRow.start_date < end),
                    ),
                )
                .limit(EVENTS_LIMIT)
            )
            events = sorted(rows.all(), key=lambda e: e.starts_at or _midnight(e.start_date, tz))  # type: ignore[arg-type]
            return tz_name, events

    def _ctx(self, actor: Actor) -> EventContext:
        return EventContext(actor.platform, actor.user_id, actor.family_id, app_version=self._app_version)


def _midnight(day: date, tz: ZoneInfo) -> datetime:
    return datetime(day.year, day.month, day.day, tzinfo=tz).astimezone(UTC)
