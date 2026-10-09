"""A fake Telegram Bot API session: records outgoing calls instead of hitting the network."""

import itertools
from datetime import UTC, datetime
from typing import Any

from aiogram import Bot
from aiogram.client.session.base import BaseSession
from aiogram.methods import GetFile, SendMessage, TelegramMethod
from aiogram.types import Chat, Document, File, Message, PhotoSize, Update, User

_ids = itertools.count(1)
FILE_BYTES = b"\xff\xd8\xff\xe0fake-jpeg"  # what every downloaded file contains


class RecordingSession(BaseSession):
    def __init__(self) -> None:
        super().__init__()
        self.sent: list[TelegramMethod[Any]] = []
        self.returned: list[Any] = []
        self.downloads: list[str] = []

    async def make_request(self, bot: Bot, method: TelegramMethod[Any], timeout: int | None = None) -> Any:  # noqa: ASYNC109 — aiogram's signature
        self.sent.append(method)
        result: Any = True
        if isinstance(method, GetFile):
            result = File(
                file_id=method.file_id, file_unique_id="u", file_size=len(FILE_BYTES), file_path="photos/file_1.jpg"
            )
        elif isinstance(method, SendMessage):
            result = Message(
                message_id=next(_ids),
                date=datetime.now(UTC),
                chat=Chat(id=int(method.chat_id), type="private"),
                text=method.text,
            )
        self.returned.append(result)
        return result

    async def stream_content(self, *args: Any, **kwargs: Any):
        self.downloads.append(kwargs.get("url", args[0] if args else ""))
        yield FILE_BYTES

    async def close(self) -> None:
        pass

    def texts(self) -> list[str]:
        return [m.text for m in self.sent if isinstance(m, SendMessage)]


def fake_bot() -> tuple[Bot, RecordingSession]:
    session = RecordingSession()
    return Bot("123456:TEST", session=session), session


def message_update(
    text: str | None,
    *,
    tg_user_id: int = 42,
    first_name: str = "Лидер",
    forwarded_at: datetime | None = None,
    reply_to_message_id: int | None = None,
    photo: bool = False,
    caption: str | None = None,
    document_mime: str | None = None,
    voice: bool = False,
) -> Update:
    from aiogram.types import MessageOriginHiddenUser, Voice

    user = User(id=tg_user_id, is_bot=False, first_name=first_name, language_code="ru")
    chat = Chat(id=tg_user_id, type="private")
    extra: dict[str, Any] = {}
    if forwarded_at is not None:
        extra["forward_origin"] = MessageOriginHiddenUser(date=forwarded_at, sender_user_name="Мама")
    if reply_to_message_id is not None:
        extra["reply_to_message"] = Message(
            message_id=reply_to_message_id, date=datetime.now(UTC), chat=chat, text="prompt"
        )
    if photo:
        # Telegram sends every size, small to large
        extra["photo"] = [
            PhotoSize(file_id=f"photo-{side}", file_unique_id=f"u{side}", width=side, height=side * 3 // 4)
            for side in (90, 320, 800, 1280, 2560)
        ]
    if document_mime is not None:
        extra["document"] = Document(
            file_id="doc", file_unique_id="udoc", mime_type=document_mime, file_size=len(FILE_BYTES)
        )
    if voice:
        extra["voice"] = Voice(file_id="voice", file_unique_id="uvoice", duration=3)
    if caption is not None:
        extra["caption"] = caption
    return Update(
        update_id=next(_ids),
        message=Message(message_id=next(_ids), date=datetime.now(UTC), chat=chat, from_user=user, text=text, **extra),
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
