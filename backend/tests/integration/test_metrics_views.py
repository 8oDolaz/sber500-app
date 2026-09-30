"""The dashboard views count real users only and do the arithmetic right."""

import uuid
from datetime import UTC, datetime
from decimal import Decimal

from sqlalchemy import text

from planner.bootstrap import Container
from planner.modules.analytics.catalog import (
    LoginHandshakeCompleted,
    OnboardingCompleted,
    Platform,
)
from planner.modules.analytics.llm_ledger import UsageEntry
from planner.modules.analytics.tracker import AnalyticsRecord, EventContext, PostgresSink
from planner.modules.identity.service import TelegramProfile


async def rows(container: Container, sql: str) -> list[dict]:
    await container.dispatcher.dispatch_batch()
    async with container.db.sessions() as s:
        return [dict(r._mapping) for r in (await s.execute(text(sql))).all()]


async def client_event(container: Container, name: str, props: dict, anon: uuid.UUID, app_version: str) -> None:
    record = AnalyticsRecord(
        id=uuid.uuid4(),
        name=name,
        schema_version=1,
        source="client",
        occurred_at=datetime.now(UTC),
        platform="pwa",
        user_id=None,
        family_id=None,
        anonymous_id=anon,
        session_id=None,
        app_version=app_version,
        properties=props,
    )
    async with container.db.transaction() as s:
        await PostgresSink().write(s, [record])


async def test_views_exclude_test_and_load_traffic(container: Container) -> None:
    real = await container.registration.handle_start(TelegramProfile(1001, "Мама"), None)
    fake = await container.registration.handle_start(TelegramProfile(1002, "Тест"), None, is_test=True)
    assert real.user_id and fake.user_id and real.family_id
    for user_id, family_id in ((real.user_id, real.family_id), (fake.user_id, fake.family_id)):
        await container.activity.record(user_id, Platform.PWA, family_id)

    # LLM spend: 0.5 ₽ by the real user; fake-provider and eval calls never count.
    for provider, feature, rub in (
        ("accelerator", "extraction", "0.5"),
        ("fake", "extraction", "9"),
        ("accelerator", "eval", "7"),
    ):
        await container.ledger.record(
            UsageEntry(
                feature,
                provider,
                "m",
                "ok",
                100,
                10,
                10,
                reported_cost_rub=Decimal(rub),
                user_id=real.user_id,
                family_id=real.family_id,
            )
        )

    [active] = await rows(container, "SELECT * FROM metrics_active_users")
    assert (active["dau"], active["wau"], active["mau"], active["active_families"]) == (1, 1, 1, 1)
    assert [r["new_users"] for r in await rows(container, "SELECT * FROM metrics_new_users")] == [1]
    assert [r["new_families"] for r in await rows(container, "SELECT * FROM metrics_new_families")] == [1]
    [cost] = await rows(container, "SELECT * FROM metrics_cost_per_dau")
    assert (cost["dau"], cost["llm_calls"], cost["cost_rub"], cost["rub_per_dau"]) == (
        1,
        1,
        Decimal("0.5000"),
        Decimal("0.5000"),
    )
    [retention] = await rows(container, "SELECT * FROM metrics_retention")
    assert retention["users"] == 1


async def test_registration_funnel_joins_pre_and_post_login(container: Container) -> None:
    anon, bot_anon = uuid.uuid4(), uuid.uuid4()
    await client_event(container, "screen_viewed", {"screen": "welcome"}, anon, "0.1.0")
    await client_event(container, "register_clicked", {}, anon, "0.1.0")
    await client_event(container, "screen_viewed", {"screen": "welcome"}, bot_anon, "loadtest")  # excluded

    started = await container.registration.handle_start(TelegramProfile(1003, "Лидер"), None)
    assert started.user_id and started.family_id
    ctx = EventContext(Platform.PWA, started.user_id, started.family_id, anonymous_id=anon)
    async with container.db.transaction() as s:
        container.tracker.track(
            s, LoginHandshakeCompleted(handshake_id=uuid.uuid4(), is_new_user=True, method="poll"), ctx
        )
        container.tracker.track(s, OnboardingCompleted(is_leader=True), ctx)

    [funnel] = await rows(container, "SELECT * FROM metrics_registration_funnel")
    assert (
        funnel["welcome_viewed"],
        funnel["register_clicked"],
        funnel["logged_in"],
        funnel["onboarding_completed"],
        funnel["first_item_created"],
    ) == (1, 1, 1, 1, 0)


async def test_every_view_is_queryable(container: Container) -> None:
    names = [
        r["table_name"]
        for r in await rows(
            container,
            "SELECT table_name FROM information_schema.views WHERE table_schema = 'public' "
            "AND (table_name LIKE 'metrics_%' OR table_name LIKE 'analytics_real_%')",
        )
    ]
    assert len(names) == 13
    for name in names:
        await rows(container, f"SELECT * FROM {name} LIMIT 1")
