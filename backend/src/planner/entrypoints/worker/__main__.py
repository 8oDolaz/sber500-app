import asyncio

from prometheus_client import start_http_server

from planner.entrypoints.worker import tasks
from planner.infra.jobs import job_app
from planner.infra.telemetry import configure_logging, configure_sentry
from planner.settings import get_settings


async def main() -> None:
    settings = get_settings()
    configure_logging(json=settings.log_json)
    configure_sentry(settings.sentry_dsn, env=settings.env, release=settings.app_version)
    start_http_server(9101)  # /metrics for the worker process
    try:
        async with job_app.open_async():
            outbox = asyncio.create_task(tasks.outbox_loop())
            try:
                await job_app.run_worker_async(concurrency=4)
            finally:
                outbox.cancel()
    finally:
        if tasks._container is not None:
            await tasks._container.aclose()


if __name__ == "__main__":
    asyncio.run(main())
