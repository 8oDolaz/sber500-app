import asyncio

from alembic import context
from sqlalchemy.ext.asyncio import create_async_engine

from planner.infra.db import Base
from planner.models import import_all_models
from planner.settings import get_settings

import_all_models()
target_metadata = Base.metadata

# analytics_events partitions are created by ensure_analytics_partitions(), not autogenerate.
EXCLUDED_TABLES = {
    "procrastinate_jobs",
    "procrastinate_events",
    "procrastinate_periodic_defers",
    "procrastinate_workers",
}


def include_object(obj, name, type_, reflected, compare_to):
    return not (type_ == "table" and (name in EXCLUDED_TABLES or (name or "").startswith("analytics_events_")))


def url() -> str:
    return context.config.get_main_option("sqlalchemy.url") or get_settings().database_url


def run_migrations_offline() -> None:
    context.configure(url=url(), target_metadata=target_metadata, literal_binds=True, include_object=include_object)
    with context.begin_transaction():
        context.run_migrations()


def do_run_migrations(connection) -> None:
    context.configure(connection=connection, target_metadata=target_metadata, include_object=include_object)
    with context.begin_transaction():
        context.run_migrations()


async def run_async_migrations() -> None:
    engine = create_async_engine(url())
    async with engine.connect() as connection:
        await connection.run_sync(do_run_migrations)
    await engine.dispose()


if context.is_offline_mode():
    run_migrations_offline()
else:
    asyncio.run(run_async_migrations())
