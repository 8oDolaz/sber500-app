import os
from collections.abc import AsyncIterator, Iterator

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import text

from planner.bootstrap import Container, build_container
from planner.modules.assistant.llm_gateway.fake import FakeProvider
from planner.settings import Settings

BACKEND_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


@pytest.fixture(scope="session")
def infra_urls() -> Iterator[tuple[str, str]]:
    """Postgres + Redis for integration tests: env vars (CI services) or throwaway containers."""
    db, redis = os.getenv("TEST_DATABASE_URL"), os.getenv("TEST_REDIS_URL")
    if db and redis:
        yield db, redis
        return
    from testcontainers.community.postgres import PostgresContainer
    from testcontainers.community.redis import RedisContainer

    with PostgresContainer("pgvector/pgvector:pg17", driver="asyncpg") as pg, RedisContainer("redis:7-alpine") as rd:
        yield pg.get_connection_url(), f"redis://{rd.get_container_host_ip()}:{rd.get_exposed_port(6379)}/0"


@pytest.fixture(scope="session")
def settings(infra_urls: tuple[str, str]) -> Settings:
    db, redis = infra_urls
    return Settings(
        _env_file=None,  # type: ignore[call-arg]
        env="test",
        database_url=db,
        redis_url=redis,
        log_json=False,
        llm_provider="fake",
        bot_token="123456:TEST",  # type: ignore[arg-type]
        bot_webhook_secret="s3cret",  # type: ignore[arg-type]
        bot_username="kainem_test_bot",
        public_app_url="https://app.test",
        enable_test_endpoints=True,
    )


@pytest.fixture(scope="session")
def migrated(settings: Settings) -> None:
    cfg = Config(os.path.join(BACKEND_DIR, "alembic.ini"))
    cfg.set_main_option("script_location", os.path.join(BACKEND_DIR, "migrations"))
    cfg.set_main_option("sqlalchemy.url", settings.database_url)
    command.upgrade(cfg, "head")


@pytest.fixture
def fake_llm() -> FakeProvider:
    return FakeProvider(models=["deepseek-v4.1-flash", "gigachat-3-pro"])


@pytest.fixture
async def container(settings: Settings, migrated: None, fake_llm: FakeProvider) -> AsyncIterator[Container]:
    c = build_container(settings, llm_provider=fake_llm)
    async with c.db.transaction() as s:
        await s.execute(
            text(
                "TRUNCATE analytics_events, user_activity_daily, llm_usage, model_prices, outbox_messages, "
                "users, identities, login_handshakes, magic_tokens, sessions, families, members, invites, "
                "bot_chats CASCADE"
            )
        )
    await c.redis.flushdb()
    try:
        yield c
    finally:
        await c.aclose()


def pytest_collection_modifyitems(items: list[pytest.Item]) -> None:
    for item in items:
        if f"{os.sep}integration{os.sep}" in str(item.path):
            item.add_marker(pytest.mark.integration)
