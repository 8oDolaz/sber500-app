"""Run the bot with long polling: locally (no public URL needed) and in production, where Telegram
cannot reach a Russian server reliably, so the bot polls through TELEGRAM_PROXY (ADR 0004)."""

import asyncio

from prometheus_client import start_http_server

from planner.bootstrap import build_container
from planner.entrypoints.bot.app import build_bot, build_dispatcher
from planner.infra.telemetry import configure_logging, configure_sentry
from planner.settings import get_settings


async def main() -> None:
    settings = get_settings()
    configure_logging(json=settings.log_json)
    configure_sentry(settings.sentry_dsn, env=settings.env, release=settings.app_version)
    bot = build_bot(settings)
    if bot is None:
        raise SystemExit("BOT_TOKEN is not set")
    start_http_server(9102)  # /metrics for the bot process
    container = build_container(settings)
    dp = build_dispatcher(container)
    try:
        await bot.delete_webhook(drop_pending_updates=False)
        await dp.start_polling(bot)
    finally:
        await container.aclose()


if __name__ == "__main__":
    asyncio.run(main())
