import uuid
from datetime import UTC, datetime, timedelta

from sqlalchemy import func, select

from planner.bootstrap import Container
from planner.infra.outbox import OutboxMessage
from planner.modules.analytics.catalog import LlmBudgetExceeded, Platform
from planner.modules.analytics.tables import AnalyticsEventRow, UserActivityDaily
from planner.modules.analytics.tracker import EventContext


async def test_tracked_event_reaches_analytics_via_outbox(container: Container) -> None:
    user_id = uuid.uuid4()
    async with container.db.transaction() as s:
        container.tracker.track(
            s,
            LlmBudgetExceeded(scope="program", model="m", feature="chat"),
            EventContext(platform=Platform.SERVER, user_id=user_id),
        )
    assert await container.dispatcher.dispatch_batch() == 1
    assert await container.dispatcher.dispatch_batch() == 0

    async with container.db.sessions() as s:
        row = (await s.scalars(select(AnalyticsEventRow))).one()
        pending = await s.scalar(select(func.count()).where(OutboxMessage.dispatched_at.is_(None)))
    assert (row.name, row.source, row.platform, row.user_id) == ("llm_budget_exceeded", "server", "server", user_id)
    assert row.properties == {"scope": "program", "model": "m", "feature": "chat"}
    assert pending == 0


async def test_event_is_not_emitted_when_transaction_rolls_back(container: Container) -> None:
    try:
        async with container.db.transaction() as s:
            container.tracker.track(
                s,
                LlmBudgetExceeded(scope="program", model="m", feature="chat"),
                EventContext(platform=Platform.SERVER),
            )
            raise RuntimeError("domain change failed")
    except RuntimeError:
        pass
    assert await container.dispatcher.dispatch_batch() == 0


async def test_failing_handler_is_retried_later(container: Container) -> None:
    calls = 0

    async def flaky(session, payload) -> None:
        nonlocal calls
        calls += 1
        if calls == 1:
            raise RuntimeError("sink down")

    container.dispatcher.register("test.flaky", flaky)
    async with container.db.transaction() as s:
        s.add(OutboxMessage(topic="test.flaky", payload={}))
    await container.dispatcher.dispatch_batch()
    async with container.db.sessions() as s:
        msg = (await s.scalars(select(OutboxMessage))).one()
        assert (msg.attempts, msg.dispatched_at) == (1, None)
        assert "sink down" in (msg.last_error or "")
    await container.dispatcher.dispatch_batch()
    async with container.db.sessions() as s:
        assert (await s.scalars(select(OutboxMessage))).one().dispatched_at is not None


async def test_events_land_in_future_month_partitions(container: Container) -> None:
    from planner.modules.analytics.tracker import AnalyticsRecord, PostgresSink

    record = AnalyticsRecord(
        id=uuid.uuid4(),
        name="screen_viewed",
        schema_version=1,
        source="client",
        occurred_at=datetime.now(UTC) + timedelta(days=62),
        platform="pwa",
        user_id=None,
        family_id=None,
        anonymous_id=uuid.uuid4(),
        session_id=None,
        app_version=None,
        properties={"screen": "home"},
    )
    async with container.db.transaction() as s:
        await PostgresSink().write(s, [record])
        await PostgresSink().write(s, [record])  # client retry: deduped
    async with container.db.sessions() as s:
        assert await s.scalar(select(func.count()).select_from(AnalyticsEventRow)) == 1


async def test_activity_is_one_row_per_user_day_platform(container: Container) -> None:
    user_id = uuid.uuid4()
    for _ in range(3):
        await container.activity.record(user_id, Platform.PWA)
    await container.activity.record(user_id, Platform.TELEGRAM_BOT)
    async with container.db.sessions() as s:
        rows = (await s.scalars(select(UserActivityDaily).where(UserActivityDaily.user_id == user_id))).all()
    assert sorted(r.platform for r in rows) == ["pwa", "telegram_bot"]
