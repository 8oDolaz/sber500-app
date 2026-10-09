"""Screens G → H through the bot: forward → draft card → «зафиксировал!»."""

import json
from datetime import UTC, datetime, timedelta

import httpx
from aiogram.methods import EditMessageText, SendMessage
from sqlalchemy import select

from planner.bootstrap import Container
from planner.modules.assistant.llm_gateway.fake import FakeProvider
from planner.modules.assistant.llm_gateway.port import LLMTimeout
from planner.modules.planning.tables import EventRow, TaskRow
from tests.integration.telegram import callback_update, fake_bot, message_update

USER = 300


def llm_json(fake: FakeProvider, payload: dict) -> None:
    fake._responder = lambda _req: json.dumps(payload, ensure_ascii=False)


async def send(client: httpx.AsyncClient, update):
    bot, session = fake_bot()
    await client.app.state.dispatcher.feed_update(bot, update)  # type: ignore[attr-defined]
    return session


def edits(session) -> list[str]:
    return [m.text or "" for m in session.sent if isinstance(m, EditMessageText)]


def sent_texts(session) -> list[str]:
    return [m.text or "" for m in session.sent if isinstance(m, SendMessage)]


def buttons(msg: SendMessage) -> dict[str, str]:
    assert msg.reply_markup is not None
    return {b.text: b.callback_data for b in msg.reply_markup.inline_keyboard[0]}  # type: ignore[union-attr]


async def register(client: httpx.AsyncClient) -> None:
    await send(client, message_update("/start", tg_user_id=USER, first_name="Дима"))


async def test_forward_confirm_says_zafiksiroval(
    client: httpx.AsyncClient, container: Container, fake_llm: FakeProvider
) -> None:
    await register(client)
    llm_json(fake_llm, {"items": [{"kind": "event", "title": "Танцы у Даши", "time": "13:00", "people": ["Даша"]}]})
    forwarded_at = datetime.now(UTC) - timedelta(days=1)
    session = await send(
        client, message_update("в 13:00 у дашки танцы забудь дим", tg_user_id=USER, forwarded_at=forwarded_at)
    )
    [card] = [m for m in session.sent if isinstance(m, SendMessage)]
    assert (card.text or "").startswith("Событие: Танцы у Даши · ")
    assert list(buttons(card)) == ["Сохранить", "Изменить", "Отмена"]
    # relative dates are resolved against the forwarded message's date
    assert f"{forwarded_at:%Y-%m-%d}" in fake_llm.calls[0].messages[1].content

    session = await send(client, callback_update(buttons(card)["Сохранить"], tg_user_id=USER))
    [edit] = edits(session)
    assert edit.startswith("зафиксировал!")
    async with container.db.sessions() as s:
        assert (await s.scalars(select(EventRow))).one().title == "Танцы у Даши"


async def test_edit_then_reply_replaces_the_card(
    client: httpx.AsyncClient, container: Container, fake_llm: FakeProvider
) -> None:
    await register(client)
    llm_json(fake_llm, {"items": [{"kind": "task", "title": "Забрать посылку", "date": "2026-09-26"}]})
    session = await send(client, message_update("забрать посылку до 26.09", tg_user_id=USER))
    [card] = [m for m in session.sent if isinstance(m, SendMessage)]

    session = await send(client, callback_update(buttons(card)["Изменить"], tg_user_id=USER))
    [prompt] = [r for m, r in zip(session.sent, session.returned, strict=True) if isinstance(m, SendMessage)]
    assert (prompt.text or "").startswith("Напишите, как правильно")

    llm_json(fake_llm, {"items": [{"kind": "task", "title": "Забрать посылку", "date": "2026-09-27"}]})
    session = await send(client, message_update("до 27.09", tg_user_id=USER, reply_to_message_id=prompt.message_id))
    [new_card] = [m for m in session.sent if isinstance(m, SendMessage)]
    assert edits(session)[0].startswith("Заменено")
    assert "27.09" in (new_card.text or "")

    session = await send(client, callback_update(buttons(new_card)["Сохранить"], tg_user_id=USER))
    async with container.db.sessions() as s:
        assert [str(t.due_date) for t in (await s.scalars(select(TaskRow))).all()] == ["2026-09-27"]


async def test_llm_down_offers_save_as_task(
    client: httpx.AsyncClient, container: Container, fake_llm: FakeProvider
) -> None:
    await register(client)
    fake_llm.fail_with = LLMTimeout("slow")
    session = await send(client, message_update("купить подарок бабушке", tg_user_id=USER))
    [card] = [m for m in session.sent if isinstance(m, SendMessage)]
    assert (card.text or "").startswith("Сейчас не получается разобрать сообщение. Сохранить его как задачу?")
    assert list(buttons(card)) == ["Сохранить как задачу", "Отмена"]
    await send(client, callback_update(buttons(card)["Сохранить как задачу"], tg_user_id=USER))
    async with container.db.sessions() as s:
        task = (await s.scalars(select(TaskRow))).one()
    assert (task.title, task.created_via) == ("купить подарок бабушке", "bot_raw")


async def test_cancel_and_stale_cards(client: httpx.AsyncClient, fake_llm: FakeProvider) -> None:
    await register(client)
    llm_json(fake_llm, {"items": [{"kind": "task", "title": "Позвонить врачу"}]})
    session = await send(client, message_update("позвонить врачу", tg_user_id=USER))
    [card] = [m for m in session.sent if isinstance(m, SendMessage)]
    session = await send(client, callback_update(buttons(card)["Отмена"], tg_user_id=USER))
    assert edits(session)[0].startswith("Отменено")
    session = await send(client, callback_update(buttons(card)["Сохранить"], tg_user_id=USER))
    assert edits(session)[0].startswith("Эта карточка устарела")


async def test_unregistered_and_unsupported(client: httpx.AsyncClient, fake_llm: FakeProvider) -> None:
    session = await send(client, message_update("купить хлеб", tg_user_id=999))
    assert sent_texts(session)[0].startswith("Сначала зарегистрируйте")
    assert fake_llm.calls == []

    await register(client)
    session = await send(client, message_update(None, tg_user_id=USER, photo=True))
    assert sent_texts(session)[0].startswith("Пока я понимаю только текст")
    assert fake_llm.calls == []


async def test_several_families_are_named_on_the_card(client: httpx.AsyncClient, fake_llm: FakeProvider) -> None:
    leader = (await client.post("/v1/test/bot-start", json={"tg_user_id": 301, "first_name": "Лидер"})).json()
    await register(client)
    token = leader["invite_link"].split("start=")[1]
    await send(client, message_update(f"/start {token}", tg_user_id=USER))
    llm_json(fake_llm, {"items": [{"kind": "task", "title": "Купить хлеб"}]})

    session = await send(client, message_update("хлеб", tg_user_id=USER))
    [card] = [m for m in session.sent if isinstance(m, SendMessage)]
    assert "в «Семья Лидер»" in (card.text or "")  # joined last → active
