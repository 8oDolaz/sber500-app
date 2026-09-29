"""Local development: run the bot with long polling (no public URL needed).
In staging/production the bot runs in webhook mode inside the API process."""

import asyncio

from planner.bootstrap import build_container
from planner.entrypoints.bot.app import build_bot, build_dispatcher
from planner.infra.telemetry import configure_logging
from planner.settings import get_settings


async def main() -> None:
    settings = get_settings()
    configure_logging(json=settings.log_json)
    bot = build_bot(settings)
    if bot is None:
        raise SystemExit("BOT_TOKEN is not set")
    container = build_container(settings)
    dp = build_dispatcher(container)
    try:
        await bot.delete_webhook(drop_pending_updates=False)
        await dp.start_polling(bot)
    finally:
        await container.aclose()


if __name__ == "__main__":
    asyncio.run(main())
