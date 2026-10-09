import uuid
from collections.abc import Awaitable, Callable
from typing import Any

from aiogram import BaseMiddleware, Bot
from aiogram.client.session.middlewares.base import BaseRequestMiddleware, NextRequestMiddlewareType
from aiogram.exceptions import TelegramForbiddenError, TelegramNetworkError, TelegramRetryAfter
from aiogram.methods import Response, TelegramMethod
from aiogram.methods.base import TelegramType
from aiogram.types import CallbackQuery, Message, TelegramObject, Update

from planner.infra.telemetry import BOT_UPDATES, TELEGRAM_API_REQUESTS
from planner.modules.analytics.activity import ActivityRecorder
from planner.modules.analytics.catalog import Platform
from planner.modules.notifications.bot_chats import BotChatService

Handler = Callable[[TelegramObject, dict[str, Any]], Awaitable[Any]]
# Telegram user id -> (our user id, active family id).
UserResolver = Callable[[int], Awaitable[tuple[uuid.UUID | None, uuid.UUID | None]]]


class MetricsMiddleware(BaseMiddleware):
    """Outer middleware on `update`: counts every update by type and outcome."""

    async def __call__(self, handler: Handler, event: TelegramObject, data: dict[str, Any]) -> Any:
        update_type = event.event_type if isinstance(event, Update) else type(event).__name__
        try:
            result = await handler(event, data)
        except Exception:
            BOT_UPDATES.labels(update_type=update_type, status="error").inc()
            raise
        BOT_UPDATES.labels(update_type=update_type, status="ok").inc()
        return result


class RequestMetricsMiddleware(BaseRequestMiddleware):
    """Session middleware: counts every Bot API call, so a dead proxy shows up as network errors."""

    async def __call__(
        self,
        make_request: NextRequestMiddlewareType[TelegramType],
        bot: Bot,
        method: TelegramMethod[TelegramType],
    ) -> Response[TelegramType]:
        name = type(method).__name__
        try:
            response = await make_request(bot, method)
        except TelegramNetworkError:
            TELEGRAM_API_REQUESTS.labels(method=name, status="network_error").inc()
            raise
        except Exception:
            TELEGRAM_API_REQUESTS.labels(method=name, status="api_error").inc()
            raise
        TELEGRAM_API_REQUESTS.labels(method=name, status="ok").inc()
        return response


class ActivityMiddleware(BaseMiddleware):
    """Messages, commands and callback presses are user-initiated activity (ADR 0003).
    `my_chat_member`, inline feedback etc. are not registered on these observers, so they never count."""

    def __init__(self, recorder: ActivityRecorder, resolve_user: UserResolver) -> None:
        self._recorder = recorder
        self._resolve = resolve_user

    async def __call__(self, handler: Handler, event: TelegramObject, data: dict[str, Any]) -> Any:
        result = await handler(event, data)
        # Resolved after the handler, so the /start that creates the user counts as that user's activity.
        if isinstance(event, Message | CallbackQuery) and event.from_user and not event.from_user.is_bot:
            user_id, family_id = await self._resolve(event.from_user.id)
            if user_id is not None:
                await self._recorder.record(user_id, Platform.TELEGRAM_BOT, family_id)
        return result


class DeliveryErrorsMiddleware(BaseMiddleware):
    """Replies that fail (user blocked the bot, flood limits) become `bot_message_failed` events."""

    def __init__(self, bot_chats: BotChatService) -> None:
        self._bot_chats = bot_chats

    async def __call__(self, handler: Handler, event: TelegramObject, data: dict[str, Any]) -> Any:
        try:
            return await handler(event, data)
        except (TelegramForbiddenError, TelegramRetryAfter) as exc:
            user = data.get("event_from_user")
            if user is None:
                raise
            reason = "forbidden" if isinstance(exc, TelegramForbiddenError) else "rate_limited"
            update_type = event.event_type if isinstance(event, Update) else "unknown"
            await self._bot_chats.delivery_failed(user.id, reason, template=update_type)
            if reason == "forbidden":
                await self._bot_chats.set_blocked(user.id, blocked=True)
                return None  # nothing to retry: Telegram would redeliver the update forever
            raise
