from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties

from planner.bootstrap import Container
from planner.entrypoints.bot import handlers
from planner.entrypoints.bot.middlewares import ActivityMiddleware, DeliveryErrorsMiddleware, MetricsMiddleware
from planner.settings import Settings


def build_bot(settings: Settings) -> Bot | None:
    token = settings.bot_token.get_secret_value()
    return Bot(token, default=DefaultBotProperties(parse_mode="HTML")) if token else None


def build_dispatcher(container: Container) -> Dispatcher:
    # Services are injected into handlers by parameter name (aiogram workflow data).
    dp = Dispatcher(registration=container.registration, bot_chats=container.bot_chats)
    dp.update.outer_middleware(MetricsMiddleware())
    dp.update.outer_middleware(DeliveryErrorsMiddleware(container.bot_chats))
    activity = ActivityMiddleware(container.activity, container.identity.resolve_telegram)
    dp.message.outer_middleware(activity)
    dp.callback_query.outer_middleware(activity)
    dp.include_router(handlers.build_router())
    return dp
