from aiogram import F, Router
from aiogram.filters import JOIN_TRANSITION, LEAVE_TRANSITION, ChatMemberUpdatedFilter, CommandObject, CommandStart
from aiogram.types import ChatMemberUpdated, LinkPreviewOptions, Message

from planner.entrypoints.bot import texts
from planner.modules.identity.service import TelegramProfile
from planner.modules.notifications.bot_chats import BotChatService
from planner.modules.registration.service import RegistrationService

NO_PREVIEW = LinkPreviewOptions(is_disabled=True)


async def start(message: Message, command: CommandObject, registration: RegistrationService) -> None:
    user = message.from_user
    if user is None or user.is_bot:
        return
    result = await registration.handle_start(
        TelegramProfile(
            tg_user_id=user.id,
            first_name=user.first_name,
            username=user.username,
            language_code=user.language_code,
        ),
        command.args,
    )
    if result.kind == "invite_not_supported_yet":
        await message.answer(texts.INVITE_SOON)
        return
    assert result.magic_link and result.invite_link
    if result.handshake_error in ("expired", "used"):
        await message.answer(texts.handshake_expired(result.magic_link), link_preview_options=NO_PREVIEW)
        return
    if result.kind == "family_registered":
        await message.answer(texts.FAMILY_REGISTERED)
        await message.answer(texts.invite(result.invite_link), link_preview_options=NO_PREVIEW)
        await message.answer(texts.finish_registration(result.magic_link), link_preview_options=NO_PREVIEW)
    else:
        await message.answer(texts.logged_in(result.magic_link), link_preview_options=NO_PREVIEW)


async def bot_blocked(event: ChatMemberUpdated, bot_chats: BotChatService) -> None:
    await bot_chats.set_blocked(event.from_user.id, blocked=True)


async def bot_unblocked(event: ChatMemberUpdated, bot_chats: BotChatService) -> None:
    await bot_chats.set_blocked(event.from_user.id, blocked=False)


def build_router() -> Router:
    """A fresh router per dispatcher (aiogram routers can be attached only once)."""
    router = Router(name="start")
    router.message.register(start, CommandStart(), F.chat.type == "private")
    router.my_chat_member.register(bot_blocked, ChatMemberUpdatedFilter(LEAVE_TRANSITION), F.chat.type == "private")
    router.my_chat_member.register(bot_unblocked, ChatMemberUpdatedFilter(JOIN_TRANSITION), F.chat.type == "private")
    return router
