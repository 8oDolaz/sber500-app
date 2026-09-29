"""A fake Telegram Bot API session: records outgoing calls instead of hitting the network."""

import itertools
from datetime import UTC, datetime
from typing import Any

from aiogram import Bot
from aiogram.client.session.base import BaseSession
from aiogram.methods import SendMessage, TelegramMethod
from aiogram.types import Chat, Message, Update, User

_ids = itertools.count(1)


class RecordingSession(BaseSession):
    def __init__(self) -> None:
        super().__init__()
        self.sent: list[TelegramMethod[Any]] = []

    async def make_request(self, bot: Bot, method: TelegramMethod[Any], timeout: int | None = None) -> Any:  # noqa: ASYNC109 — aiogram's signature
        self.sent.append(method)
        if isinstance(method, SendMessage):
            return Message(
                message_id=next(_ids),
                date=datetime.now(UTC),
                chat=Chat(id=int(method.chat_id), type="private"),
                text=method.text,
            )
        return True

    async def stream_content(self, *args: Any, **kwargs: Any):  # pragma: no cover
        raise NotImplementedError
        yield b""

    async def close(self) -> None:
        pass

    def texts(self) -> list[str]:
        return [m.text for m in self.sent if isinstance(m, SendMessage)]


def fake_bot() -> tuple[Bot, RecordingSession]:
    session = RecordingSession()
    return Bot("123456:TEST", session=session), session


def message_update(text: str, *, tg_user_id: int = 42, first_name: str = "Лидер") -> Update:
    user = User(id=tg_user_id, is_bot=False, first_name=first_name, language_code="ru")
    return Update(
        update_id=next(_ids),
        message=Message(
            message_id=next(_ids),
            date=datetime.now(UTC),
            chat=Chat(id=tg_user_id, type="private"),
            from_user=user,
            text=text,
        ),
    )
