import uuid
from datetime import date, datetime

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel

from planner.entrypoints.api.deps import ContainerDep, MemberDep, PlatformDep
from planner.modules.planning.service import Actor
from planner.modules.planning.tables import EventRow, TaskRow

router = APIRouter(prefix="/v1/families/{family_id}", tags=["planning"])


class TaskOut(BaseModel):
    id: uuid.UUID
    title: str
    due_date: date | None
    due_at: datetime | None
    assignee_hint: str | None
    done: bool

    @classmethod
    def of(cls, t: TaskRow) -> "TaskOut":
        return cls(
            id=t.id,
            title=t.title,
            due_date=t.due_date,
            due_at=t.due_at,
            assignee_hint=t.assignee_hint,
            done=t.status == "done",
        )


class EventOut(BaseModel):
    id: uuid.UUID
    title: str
    all_day: bool
    starts_at: datetime | None
    ends_at: datetime | None
    start_date: date | None
    participants_hint: str | None

    @classmethod
    def of(cls, e: EventRow) -> "EventOut":
        return cls(
            id=e.id,
            title=e.title,
            all_day=e.all_day,
            starts_at=e.starts_at,
            ends_at=e.ends_at,
            start_date=e.start_date,
            participants_hint=e.participants_hint,
        )


class EventsOut(BaseModel):
    timezone: str  # render times in the family's zone
    events: list[EventOut]


class TaskUpdate(BaseModel):
    done: bool


@router.get("/tasks", response_model=list[TaskOut])
async def list_open_tasks(family_id: uuid.UUID, member: MemberDep, c: ContainerDep) -> list[TaskOut]:
    return [TaskOut.of(t) for t in await c.planning.open_tasks(family_id)]


@router.patch("/tasks/{task_id}", response_model=TaskOut)
async def update_task(
    family_id: uuid.UUID,
    task_id: uuid.UUID,
    body: TaskUpdate,
    member: MemberDep,
    c: ContainerDep,
    platform: PlatformDep,
) -> TaskOut:
    """Tap on the list dot: mark done (or undo)."""
    task = await c.planning.set_task_done(Actor(member.user_id, family_id, platform), task_id, body.done)
    if task is None:
        raise HTTPException(404, "task not found")
    return TaskOut.of(task)


@router.get("/events", response_model=EventsOut)
async def upcoming_events(
    family_id: uuid.UUID, member: MemberDep, c: ContainerDep, days: int = Query(default=7, ge=1, le=31)
) -> EventsOut:
    tz, events = await c.planning.upcoming_events(family_id, days)
    return EventsOut(timezone=tz, events=[EventOut.of(e) for e in events])
