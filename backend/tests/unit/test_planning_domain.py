from datetime import UTC, date, datetime

import pytest

from planner.domain.planning import NewEvent, NewTask, PlanningError


def test_task_title_is_normalized_and_due_date_follows_due_at() -> None:
    t = NewTask("  забрать   посылку ", due_at=datetime(2026, 9, 26, 15, tzinfo=UTC), assignee_hint="  дим ")
    assert t.title == "забрать посылку"
    assert t.due_date == date(2026, 9, 26)
    assert t.assignee_hint == "дим"


@pytest.mark.parametrize(
    "kwargs",
    [
        {"title": "   "},
        {"title": "x", "due_at": datetime(2026, 9, 26, 15)},  # naive
    ],
)
def test_invalid_tasks(kwargs) -> None:
    with pytest.raises(PlanningError):
        NewTask(**kwargs)


def test_event_is_timed_xor_all_day() -> None:
    assert NewEvent("танцы", starts_at=datetime(2026, 9, 30, 10, tzinfo=UTC)).all_day is False
    assert NewEvent("день рождения", start_date=date(2026, 10, 2)).all_day is True
    with pytest.raises(PlanningError):
        NewEvent("?")
    with pytest.raises(PlanningError):
        NewEvent("?", starts_at=datetime(2026, 9, 30, tzinfo=UTC), start_date=date(2026, 9, 30))
    with pytest.raises(PlanningError):
        NewEvent("?", starts_at=datetime(2026, 9, 30, 12, tzinfo=UTC), ends_at=datetime(2026, 9, 30, 11, tzinfo=UTC))
