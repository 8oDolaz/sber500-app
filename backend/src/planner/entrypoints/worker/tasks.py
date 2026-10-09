import asyncio

import structlog
from procrastinate import JobContext, builtin_tasks
from sqlalchemy import text

from planner.bootstrap import Container, build_container
from planner.infra.jobs import job_app
from planner.modules.analytics.price_sync import apply_quotes, fetch_from_proxy
from planner.settings import get_settings

log = structlog.get_logger(__name__)

_container: Container | None = None


def container() -> Container:
    global _container
    if _container is None:
        _container = build_container(get_settings())
    return _container


async def outbox_loop(poll_interval_s: float = 1.0) -> None:
    """Runs next to the Procrastinate worker (a job every second would bloat the jobs table)."""
    c = container()
    while True:
        try:
            while await c.dispatcher.dispatch_batch() == 200:
                pass
        except Exception as exc:  # noqa: BLE001 — keep the loop alive; errors are logged and retried
            log.error("outbox.loop_failed", error=repr(exc))
        await asyncio.sleep(poll_interval_s)


@job_app.periodic(cron="45 3 * * *", periodic_id="remove_old_jobs")
@job_app.task(queue="maintenance", pass_context=True)
async def remove_old_jobs(context: JobContext, timestamp: int) -> None:
    await builtin_tasks.remove_old_jobs(context, max_hours=72, remove_failed=False)


@job_app.periodic(cron="0 3 * * *", periodic_id="ensure_analytics_partitions")
@job_app.task(queue="maintenance")
async def ensure_analytics_partitions(timestamp: int) -> None:
    async with container().db.transaction() as s:
        await s.execute(text("SELECT ensure_analytics_partitions(3)"))


@job_app.periodic(cron="15 3 * * *", periodic_id="purge_outbox")
@job_app.task(queue="maintenance")
async def purge_outbox(timestamp: int) -> None:
    await container().dispatcher.purge_dispatched(older_than_days=7)


@job_app.periodic(cron="*/15 * * * *", periodic_id="check_llm_spend")
@job_app.task(queue="maintenance")
async def check_llm_spend(timestamp: int) -> None:
    spent = await container().spend_monitor.check()
    log.info("llm.spend_checked", spent_rub=str(spent))


@job_app.periodic(cron="30 3 * * *", periodic_id="sync_model_prices")
@job_app.task(queue="maintenance")
async def sync_model_prices(timestamp: int) -> None:
    s = get_settings()
    if s.llm_provider != "openai_compatible":
        return
    try:
        quotes = await fetch_from_proxy(s.llm_base_url, s.llm_api_key.get_secret_value())
    except Exception as exc:  # noqa: BLE001 — the proxy may not expose prices; proxy-reported cost still works
        log.warning("llm.price_sync_failed", error=repr(exc))
        return
    changed = await apply_quotes(container().db, quotes, provider="accelerator", source="proxy_model_info")
    log.info("llm.price_sync_done", changed=changed)


@job_app.periodic(cron="20 3 * * *", periodic_id="purge_auth_artifacts")
@job_app.task(queue="maintenance")
async def purge_auth_artifacts(timestamp: int) -> None:
    """Expired login handshakes / magic links / sessions are useless after a grace period."""
    async with container().db.transaction() as s:
        await s.execute(text("DELETE FROM login_handshakes WHERE expires_at < now() - interval '2 days'"))
        await s.execute(text("DELETE FROM magic_tokens WHERE expires_at < now() - interval '2 days'"))
        await s.execute(text("DELETE FROM sessions WHERE expires_at < now() - interval '7 days'"))


@job_app.periodic(cron="*/10 * * * *", periodic_id="expire_draft_actions")
@job_app.task(queue="maintenance")
async def expire_draft_actions(timestamp: int) -> None:
    expired = await container().capture.expire()
    if expired:
        log.info("drafts.expired", count=expired)
