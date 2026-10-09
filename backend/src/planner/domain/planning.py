"""Tasks and events (ARCHITECTURE §5.2, §7.5). Pure: no I/O, no frameworks.

Time rules: instants are stored in UTC together with the family's IANA timezone;
all-day events and task due dates are dates, not timestamps.
"""

from dataclasses import dataclass
from datetime import date, datetime, timedelta
from enum import StrEnum

TITLE_MAX = 300
HINT_MAX = 120


class CreatedVia(StrEnum):
    UI = "ui"
    BOT_DRAFT = "bot_draft"  # extracted by the assistant, confirmed by the user
    BOT_RAW = "bot_raw"  # the message saved as-is (LLM unavailable or found nothing)


class PlanningError(ValueError):
    pass


def clean_title(title: str) -> str:
    title = " ".join(title.split())
    if not title:
        raise PlanningError("empty title")
    return title[:TITLE_MAX]


def clean_hint(hint: str | None) -> str | None:
    hint = " ".join((hint or "").split())
    return hint[:HINT_MAX] or None


@dataclass(frozen=True, slots=True)
class NewTask:
    title: str
    due_date: date | None = None
    due_at: datetime | None = None  # a time was given ("до 18:00"); aware datetime
    assignee_hint: str | None = None  # a name as written ("дим"); matched to members later

    def __post_init__(self) -> None:
        object.__setattr__(self, "title", clean_title(self.title))
        object.__setattr__(self, "assignee_hint", clean_hint(self.assignee_hint))
        if self.due_at is not None:
            if self.due_at.tzinfo is None:
                raise PlanningError("due_at must be timezone-aware")
            object.__setattr__(self, "due_date", self.due_at.date() if self.due_date is None else self.due_date)


@dataclass(frozen=True, slots=True)
class NewEvent:
    title: str
    starts_at: datetime | None = None  # timed event, aware datetime
    ends_at: datetime | None = None
    start_date: date | None = None  # all-day event
    participants_hint: str | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "title", clean_title(self.title))
        object.__setattr__(self, "participants_hint", clean_hint(self.participants_hint))
        if (self.starts_at is None) == (self.start_date is None):
            raise PlanningError("an event needs either a start time or an all-day date")
        for value in (self.starts_at, self.ends_at):
            if value is not None and value.tzinfo is None:
                raise PlanningError("event times must be timezone-aware")
        if self.ends_at is not None:
            if self.starts_at is None:
                raise PlanningError("an all-day event has no end time")
            if self.ends_at < self.starts_at:
                raise PlanningError("event ends before it starts")

    @property
    def all_day(self) -> bool:
        return self.start_date is not None


def upcoming_window(today: date, days: int) -> tuple[date, date]:
    """Dates [today, today + days) in the family's timezone."""
    return today, today + timedelta(days=days)
