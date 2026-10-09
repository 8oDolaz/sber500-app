import pytest
from aiogram.client.session.aiohttp import AiohttpSession
from aiogram.exceptions import TelegramNetworkError
from aiogram.methods import GetMe
from pydantic import SecretStr

from planner.entrypoints.bot.app import build_bot
from planner.entrypoints.bot.middlewares import RequestMetricsMiddleware
from planner.infra.telemetry import TELEGRAM_API_REQUESTS
from planner.settings import Settings


async def test_no_token_means_no_bot() -> None:
    assert build_bot(Settings(bot_token=SecretStr(""))) is None


async def test_bot_connects_directly_without_a_proxy() -> None:
    bot = build_bot(Settings(bot_token=SecretStr("1:x"), telegram_proxy=""))
    assert bot is not None
    assert isinstance(bot.session, AiohttpSession)
    assert bot.session.proxy is None
    await bot.session.close()


async def test_bot_uses_the_configured_proxy() -> None:
    bot = build_bot(Settings(bot_token=SecretStr("1:x"), telegram_proxy="socks5://xray:1080"))
    assert bot is not None
    assert isinstance(bot.session, AiohttpSession)
    assert bot.session.proxy == "socks5://xray:1080"
    await bot.session.close()


async def test_unreachable_bot_api_is_counted_as_a_network_error() -> None:
    def count(status: str) -> float:
        return TELEGRAM_API_REQUESTS.labels(method="GetMe", status=status)._value.get()

    async def unreachable(bot, method):  # type: ignore[no-untyped-def]
        raise TelegramNetworkError(method=method, message="Request timeout error")

    before = count("network_error")
    with pytest.raises(TelegramNetworkError):
        await RequestMetricsMiddleware()(unreachable, None, GetMe())  # type: ignore[arg-type]
    assert count("network_error") == before + 1
