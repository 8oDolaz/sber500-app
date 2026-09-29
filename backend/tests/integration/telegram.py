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


def _user(tg_user_id: int, first_name: str) -> User:
    return User(id=tg_user_id, is_bot=False, first_name=first_name, language_code="ru")


def inline_query_update(query: str, *, tg_user_id: int = 42) -> Update:
    from aiogram.types import InlineQuery

    return Update(
        update_id=next(_ids),
        inline_query=InlineQuery(id=str(next(_ids)), from_user=_user(tg_user_id, "Лидер"), query=query, offset=""),
    )


def chosen_inline_update(result_id: str, *, tg_user_id: int = 42) -> Update:
    from aiogram.types import ChosenInlineResult

    return Update(
        update_id=next(_ids),
        chosen_inline_result=ChosenInlineResult(
            result_id=result_id, from_user=_user(tg_user_id, "Лидер"), query="invite"
        ),
    )


def callback_update(data: str, *, tg_user_id: int = 42, first_name: str = "Лидер") -> Update:
    from aiogram.types import CallbackQuery

    return Update(
        update_id=next(_ids),
        callback_query=CallbackQuery(
            id=str(next(_ids)),
            from_user=_user(tg_user_id, first_name),
            chat_instance="ci",
            data=data,
            message=Message(
                message_id=next(_ids),
                date=datetime.now(UTC),
                chat=Chat(id=tg_user_id, type="private"),
                text="…",
            ),
        ),
    )
