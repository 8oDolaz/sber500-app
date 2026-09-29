"""Bot capture: messages → draft cards → «зафиксировал!» (SPEC screens G → H)."""

import uuid
from datetime import datetime

from aiogram import Bot, F, Router
from aiogram.filters import Filter
from aiogram.types import CallbackQuery, ForceReply, InlineKeyboardButton, InlineKeyboardMarkup, Message
from redis.asyncio import Redis

from planner.entrypoints.bot import texts
from planner.infra.ratelimit import RateLimiter
from planner.modules.assistant.capture import CaptureOutcome, CaptureService
from planner.modules.families.service import FamilyService
from planner.modules.identity.service import IdentityService

CAPTURES_PER_MIN = 20
REVISE_TTL_S = 30 * 60


def cb(action: str, draft_id: uuid.UUID) -> str:
    return f"d:{action}:{draft_id}"  # ≤ 64 bytes


def card_keyboard(draft_id: uuid.UUID, raw: bool) -> InlineKeyboardMarkup:
    if raw:
        row = [
            InlineKeyboardButton(text=texts.SAVE_AS_TASK, callback_data=cb("c", draft_id)),
            InlineKeyboardButton(text=texts.CANCEL, callback_data=cb("x", draft_id)),
        ]
    else:
        row = [
            InlineKeyboardButton(text=texts.SAVE, callback_data=cb("c", draft_id)),
            InlineKeyboardButton(text=texts.EDIT, callback_data=cb("e", draft_id)),
            InlineKeyboardButton(text=texts.CANCEL, callback_data=cb("x", draft_id)),
        ]
    return InlineKeyboardMarkup(inline_keyboard=[row])


def revise_key(chat_id: int, prompt_message_id: int) -> str:
    return f"bot:revise:{chat_id}:{prompt_message_id}"


class IsRevision(Filter):
    """A reply to our «Напишите, как правильно» prompt."""

    async def __call__(self, message: Message, redis: Redis) -> bool | dict:
        reply = message.reply_to_message
        if reply is None or message.text is None:
            return False
        value = await redis.get(revise_key(message.chat.id, reply.message_id))
        if value is None:
            return False
        draft_id, card_message_id = str(value).split(":")  # the client decodes responses
        return {"revise_draft_id": uuid.UUID(draft_id), "revise_card_message_id": int(card_message_id)}


async def family_label(families: FamilyService, user_id: uuid.UUID, family_id: uuid.UUID) -> str | None:
    """Name the family on the card only when the user has several."""
    mine = await families.my_families(user_id)
    if len(mine) < 2:
        return None
    return next((f.name for f in mine if f.id == family_id), None)


async def send_outcome(message: Message, outcome: CaptureOutcome, family: str | None) -> None:
    if outcome.failure is not None:
        [draft] = outcome.drafts
        await message.answer(texts.fallback(outcome.failure, draft.summary), reply_markup=card_keyboard(draft.id, True))
        return
    for draft in outcome.drafts:
        await message.answer(texts.draft_card(draft.summary, family), reply_markup=card_keyboard(draft.id, False))


async def capture_text(
    message: Message,
    bot: Bot,
    capture: CaptureService,
    identity: IdentityService,
    families: FamilyService,
    rate_limiter: RateLimiter,
) -> None:
    assert message.from_user is not None and message.text is not None
    user_id, family_id = await identity.resolve_telegram(message.from_user.id)
    if user_id is None or family_id is None:
        await message.answer(texts.NOT_REGISTERED)
        return
    if not await rate_limiter.hit(f"capture:{message.from_user.id}", CAPTURES_PER_MIN):
        await message.answer(texts.TOO_FAST)
        return
    await bot.send_chat_action(message.chat.id, "typing")
    forwarded = message.forward_origin is not None
    written_at: datetime = message.forward_origin.date if message.forward_origin else message.date
    outcome = await capture.capture(
        user_id=user_id,
        family_id=family_id,
        text=message.text,
        source="forwarded" if forwarded else "own",
        written_at=written_at,
    )
    await send_outcome(message, outcome, await family_label(families, user_id, family_id))


async def capture_unsupported(message: Message, capture: CaptureService, identity: IdentityService) -> None:
    assert message.from_user is not None
    user_id, family_id = await identity.resolve_telegram(message.from_user.id)
    if user_id is None or family_id is None:
        await message.answer(texts.NOT_REGISTERED)
        return
    kind = "photo" if message.photo else "voice" if (message.voice or message.video_note) else "other"
    await capture.record_unsupported(
        user_id=user_id,
        family_id=family_id,
        source="forwarded" if message.forward_origin else "own",
        content_type=kind,
    )
    await message.answer(texts.UNSUPPORTED)


async def revise(
    message: Message,
    bot: Bot,
    redis: Redis,
    revise_draft_id: uuid.UUID,
    revise_card_message_id: int,
    capture: CaptureService,
    identity: IdentityService,
    families: FamilyService,
) -> None:
    assert message.from_user is not None and message.text is not None and message.reply_to_message is not None
    await redis.delete(revise_key(message.chat.id, message.reply_to_message.message_id))
    user_id, family_id = await identity.resolve_telegram(message.from_user.id)
    if user_id is None or family_id is None:
        return
    await bot.send_chat_action(message.chat.id, "typing")
    outcome = await capture.revise(revise_draft_id, user_id, message.text)
    if outcome is None:
        await message.answer(texts.CARD_GONE)
        return
    await bot.edit_message_text(texts.REPLACED, chat_id=message.chat.id, message_id=revise_card_message_id)
    await send_outcome(message, outcome, await family_label(families, user_id, family_id))


async def on_card_button(
    callback: CallbackQuery, bot: Bot, redis: Redis, capture: CaptureService, identity: IdentityService
) -> None:
    assert callback.data is not None
    _, action, raw_id = callback.data.split(":", 2)
    draft_id = uuid.UUID(raw_id)
    user_id, _ = await identity.resolve_telegram(callback.from_user.id)
    card = callback.message if isinstance(callback.message, Message) else None
    if user_id is None or card is None:
        await callback.answer(texts.CARD_GONE, show_alert=True)
        return

    if action == "c":
        result = await capture.confirm(draft_id, user_id)
        if result.status == "already":
            await callback.answer(texts.ALREADY_SAVED)
            return
        await callback.answer()
        await card.edit_text(texts.saved(result.summary) if result.status == "done" else texts.CARD_GONE)
    elif action == "x":
        result = await capture.cancel(draft_id, user_id)
        await callback.answer()
        await card.edit_text(texts.cancelled(result.summary) if result.status == "done" else texts.CARD_GONE)
    elif action == "e":
        if not await capture.can_revise(draft_id, user_id):
            await callback.answer()
            await card.edit_text(texts.CARD_GONE)
            return
        await callback.answer()
        prompt = await bot.send_message(
            card.chat.id, texts.REVISE_PROMPT, reply_markup=ForceReply(input_field_placeholder="в пятницу в 18:00")
        )
        await redis.set(revise_key(card.chat.id, prompt.message_id), f"{draft_id}:{card.message_id}", ex=REVISE_TTL_S)
    else:
        await callback.answer()


def build_router() -> Router:
    router = Router(name="capture")
    private = F.chat.type == "private"
    router.message.register(revise, private, F.text, IsRevision())
    router.message.register(capture_text, private, F.text, ~F.text.startswith("/"))
    router.message.register(capture_unsupported, private, F.photo | F.voice | F.video_note | F.document | F.video)
    router.callback_query.register(on_card_button, F.data.startswith("d:"))
    return router
