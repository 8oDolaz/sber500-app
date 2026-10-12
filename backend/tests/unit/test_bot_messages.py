from dataclasses import replace

import pytest
from aiogram.methods import SendMessage
from aiogram.types import LinkPreviewOptions

from planner.entrypoints.bot.handlers import reply_to_start
from planner.modules.registration.service import StartResult
from tests.integration.telegram import fake_bot, message_update


@pytest.mark.parametrize(
    "result",
    [
        StartResult(kind="family_registered"),
        StartResult(kind="logged_in"),
        StartResult(kind="invite_accepted"),
        StartResult(kind="invite_already_member"),
        StartResult(kind="logged_in", handshake_error="expired"),
        StartResult(kind="logged_in", handshake_error="used"),
        StartResult(kind="family_registered", handshake_error="used"),
    ],
)
async def test_every_space_message_has_a_separate_invite_paragraph(result: StartResult) -> None:
    result = replace(
        result,
        family_name="<Семья & друзья>",
        magic_link="https://app.test/auth/tg?token=private_login",
        invite_link="https://t.me/kainem_test_bot?start=inv_public_invite",
    )
    bot, session = fake_bot()
    update = message_update("/start")
    assert update.message is not None
    await reply_to_start(update.message.as_(bot), result)
    replies = session.texts()
    assert len(replies) == (3 if result.kind == "family_registered" else 1)
    assert "https://app.test/auth/tg?token=private_login\n\n" in replies[-1]
    assert "Отправь эту ссылку близким" in replies[-1]
    assert replies[-1].endswith("https://t.me/kainem_test_bot?start=inv_public_invite")
    assert "<Семья & друзья>" not in replies[-1]  # Telegram HTML must not interpret the family name as markup.
    if result.kind == "family_registered":
        assert replies[0] == "<b>Пространство семьи зарегистрировано!</b>"
        assert replies[1].startswith("Отправь эту ссылку близким")
        assert "private_login" not in replies[1]  # forwarding the invite must never forward a login token.
        invite = session.sent[1]
        assert isinstance(invite, SendMessage) and invite.reply_markup is not None
        assert isinstance(invite.link_preview_options, LinkPreviewOptions) and invite.link_preview_options.is_disabled
