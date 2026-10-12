import uuid

from aiogram import F, Router
from aiogram.filters import (
    JOIN_TRANSITION,
    LEAVE_TRANSITION,
    ChatMemberUpdatedFilter,
    Command,
    CommandObject,
    CommandStart,
)
from aiogram.types import (
    CallbackQuery,
    ChatMemberUpdated,
    ChosenInlineResult,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    InlineQuery,
    InlineQueryResultArticle,
    InlineQueryResultsButton,
    InputTextMessageContent,
    LinkPreviewOptions,
    Message,
    SwitchInlineQueryChosenChat,
    User,
)

from planner.domain.families import SHARE_INVITE_START_PAYLOAD
from planner.entrypoints.bot import texts
from planner.modules.identity.service import TelegramProfile
from planner.modules.notifications.bot_chats import BotChatService
from planner.modules.registration.service import RegistrationService, StartResult

NO_PREVIEW = LinkPreviewOptions(is_disabled=True)
REGISTER_OWN = "register_own"
SHARE_QUERY = "invite"


def profile_of(user: User) -> TelegramProfile:
    return TelegramProfile(
        tg_user_id=user.id, first_name=user.first_name, username=user.username, language_code=user.language_code
    )


def share_keyboard() -> InlineKeyboardMarkup:
    """E2's share button: pick a chat, the bot inserts an invite card (tracked as invite_shared)."""
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text=texts.SHARE,
                    switch_inline_query_chosen_chat=SwitchInlineQueryChosenChat(
                        query=SHARE_QUERY, allow_user_chats=True, allow_group_chats=True
                    ),
                )
            ]
        ]
    )


async def send_invite(message: Message, invite_link: str) -> None:
    await message.answer(texts.invite(invite_link), link_preview_options=NO_PREVIEW, reply_markup=share_keyboard())


async def reply_to_start(message: Message, result: StartResult) -> None:
    if result.kind == "invite_invalid":
        await message.answer(
            texts.INVITE_INVALID,
            reply_markup=InlineKeyboardMarkup(
                inline_keyboard=[[InlineKeyboardButton(text=texts.CREATE_OWN_FAMILY, callback_data=REGISTER_OWN)]]
            ),
        )
        return
    assert result.magic_link and result.invite_link and result.family_name
    if result.kind == "family_registered":
        await message.answer(texts.FAMILY_REGISTERED)
        await send_invite(message, result.invite_link)
    if result.kind == "invite_accepted":
        await message.answer(
            texts.invite_accepted(result.family_name, result.magic_link, result.invite_link),
            link_preview_options=NO_PREVIEW,
        )
    elif result.kind == "invite_already_member":
        await message.answer(
            texts.already_member(result.family_name, result.magic_link, result.invite_link),
            link_preview_options=NO_PREVIEW,
        )
    elif result.handshake_error in ("expired", "used"):
        await message.answer(
            texts.handshake_expired(result.magic_link, result.invite_link), link_preview_options=NO_PREVIEW
        )
    elif result.kind == "family_registered":
        await message.answer(
            texts.finish_registration(result.magic_link, result.invite_link), link_preview_options=NO_PREVIEW
        )
    else:
        await message.answer(texts.logged_in(result.magic_link, result.invite_link), link_preview_options=NO_PREVIEW)


async def start(message: Message, command: CommandObject, registration: RegistrationService) -> None:
    if message.from_user is None or message.from_user.is_bot:
        return
    if (command.args or "").strip() == SHARE_INVITE_START_PAYLOAD:
        await invite_command(message, registration)
        return
    await reply_to_start(message, await registration.handle_start(profile_of(message.from_user), command.args))


async def register_own(callback: CallbackQuery, registration: RegistrationService) -> None:
    """After a dead invite link: "Создать своё пространство"."""
    await callback.answer()
    if isinstance(callback.message, Message):
        await reply_to_start(callback.message, await registration.handle_start(profile_of(callback.from_user), None))


async def invite_command(message: Message, registration: RegistrationService) -> None:
    """/invite: re-send the active family's invite with the share button."""
    if message.from_user is None:
        return
    shared = await registration.invite_for_sharing(message.from_user.id)
    if shared is None:
        await message.answer(texts.NOT_REGISTERED)
        return
    await send_invite(message, registration.invite_link(shared.invite.token))


async def inline_invite(query: InlineQuery, registration: RegistrationService) -> None:
    shared = await registration.invite_for_sharing(query.from_user.id)
    if shared is None:
        await query.answer(
            [],
            cache_time=0,
            is_personal=True,
            button=InlineQueryResultsButton(text=texts.INLINE_REGISTER, start_parameter="from_inline"),
        )
        return
    link = registration.invite_link(shared.invite.token)
    card = InlineQueryResultArticle(
        id=str(shared.invite.id),  # comes back in chosen_inline_result → invite_shared
        title=texts.INLINE_TITLE.format(family=shared.family.name),
        description=texts.INLINE_DESCRIPTION,
        input_message_content=InputTextMessageContent(
            message_text=texts.invite_card(shared.family.name, link), link_preview_options=NO_PREVIEW
        ),
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text=texts.JOIN, url=link)]]),
    )
    await query.answer([card], cache_time=0, is_personal=True)


async def invite_shared(result: ChosenInlineResult, registration: RegistrationService) -> None:
    try:
        invite_id = uuid.UUID(result.result_id)
    except ValueError:
        return
    await registration.record_invite_shared(result.from_user.id, invite_id)


async def bot_blocked(event: ChatMemberUpdated, bot_chats: BotChatService) -> None:
    await bot_chats.set_blocked(event.from_user.id, blocked=True)


async def bot_unblocked(event: ChatMemberUpdated, bot_chats: BotChatService) -> None:
    await bot_chats.set_blocked(event.from_user.id, blocked=False)


def build_router() -> Router:
    """A fresh router per dispatcher (aiogram routers can be attached only once)."""
    router = Router(name="start")
    private = F.chat.type == "private"
    router.message.register(start, CommandStart(), private)
    router.message.register(invite_command, Command("invite"), private)
    router.callback_query.register(register_own, F.data == REGISTER_OWN)
    router.inline_query.register(inline_invite)
    router.chosen_inline_result.register(invite_shared)
    router.my_chat_member.register(bot_blocked, ChatMemberUpdatedFilter(LEAVE_TRANSITION), private)
    router.my_chat_member.register(bot_unblocked, ChatMemberUpdatedFilter(JOIN_TRANSITION), private)
    return router
