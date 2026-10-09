from datetime import UTC, date, datetime

import pytest

from planner.domain.planning import NewEvent, NewTask
from planner.modules.assistant.capture import summarize
from planner.modules.assistant.extraction import (
    ExtractedItem,
    ExtractionContext,
    InvalidOutput,
    parse_output,
    to_command,
    user_prompt,
)

# 2026-09-29 10:00 Moscow (Tuesday)
CTX = ExtractionContext(
    reference=datetime(2026, 9, 29, 7, 0, tzinfo=UTC), timezone="Europe/Moscow", member_names=["Даша", "Дима"]
)


def test_parse_tolerates_code_fences_and_prose() -> None:
    out = parse_output('Вот ответ:\n```json\n{"items": [{"kind": "task", "title": "Купить хлеб"}]}\n```')
    assert out.items[0].title == "Купить хлеб" and out.items[0].day is None


@pytest.mark.parametrize(
    "text",
    [
        "not json",
        '{"items": [{"kind": "reminder", "title": "x"}]}',
        '{"items": [{"kind": "task", "title": "x", "time": "25:00"}]}',
    ],
)
def test_parse_rejects_invalid(text: str) -> None:
    with pytest.raises(InvalidOutput):
        parse_output(text)


def test_prompt_contains_reference_date_members_and_fenced_message() -> None:
    p = user_prompt("в 13:00 у дашки танцы", CTX)
    assert "2026-09-29 (вторник), время 10:00" in p
    assert "Даша, Дима" in p
    assert "<message>\nв 13:00 у дашки танцы\n</message>" in p


def test_timed_event_without_date_is_on_the_message_day() -> None:
    cmd = to_command(ExtractedItem(kind="event", title="Танцы у Даши", time="13:00", people=["Даша", "Дима"]), CTX)
    assert isinstance(cmd, NewEvent)
    assert cmd.starts_at == datetime(2026, 9, 29, 10, 0, tzinfo=UTC)  # 13:00 MSK
    assert cmd.participants_hint == "Даша, Дима"
    assert summarize(cmd, "Europe/Moscow") == "Событие: Танцы у Даши · вт 29.09 в 13:00 · Даша, Дима"


def test_dated_event_without_time_is_all_day() -> None:
    cmd = to_command(ExtractedItem(kind="event", title="День рождения бабушки", date=date(2026, 10, 2)), CTX)
    assert isinstance(cmd, NewEvent) and cmd.start_date == date(2026, 10, 2)
    assert summarize(cmd, "Europe/Moscow") == "Событие: День рождения бабушки · пт 02.10, весь день"


def test_event_without_any_date_becomes_a_task() -> None:
    assert isinstance(to_command(ExtractedItem(kind="event", title="Созвониться"), CTX), NewTask)


def test_task_with_deadline() -> None:
    cmd = to_command(ExtractedItem(kind="task", title="Забрать посылку", date=date(2026, 9, 26)), CTX)
    assert isinstance(cmd, NewTask) and cmd.due_date == date(2026, 9, 26)
    assert summarize(cmd, "Europe/Moscow") == "Задача: Забрать посылку · до сб 26.09"


def test_end_before_start_is_dropped() -> None:
    cmd = to_command(
        ExtractedItem(kind="event", title="Врач", date=date(2026, 9, 30), time="16:00", end_time="15:00"), CTX
    )
    assert isinstance(cmd, NewEvent) and cmd.ends_at is None
