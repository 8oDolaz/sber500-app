"""M3: invite links, the acceptor flow (screen F), sharing, several families."""

import re
import uuid

import httpx
from aiogram.methods import AnswerInlineQuery, SendMessage
from sqlalchemy import select

from planner.bootstrap import Container
from planner.modules.analytics.tables import AnalyticsEventRow
from planner.modules.families.tables import InviteRow, MemberRow
from planner.modules.identity.tables import UserRow
from tests.integration.telegram import (
    callback_update,
    chosen_inline_update,
    fake_bot,
    inline_query_update,
    message_update,
)

LEADER, ACCEPTOR = 100, 200
PWA = {"X-Client-Platform": "pwa"}


async def send(client: httpx.AsyncClient, update) -> list:
    bot, session = fake_bot()
    await client.app.state.dispatcher.feed_update(bot, update)  # type: ignore[attr-defined]
    return session.sent


def texts(sent: list) -> list[str]:
    return [m.text for m in sent if isinstance(m, SendMessage)]


async def register_leader(client: httpx.AsyncClient) -> str:
    sent = await send(client, message_update("/start", tg_user_id=LEADER, first_name="Лидер"))
    invite_msg = sent[1]
    assert isinstance(invite_msg, SendMessage)
    # E2 carries the share button (inline mode, pick a chat)
    button = invite_msg.reply_markup.inline_keyboard[0][0]  # type: ignore[union-attr]
    assert button.text == "Поделиться"
    assert button.switch_inline_query_chosen_chat is not None
    assert button.switch_inline_query_chosen_chat.query == "invite"
    match = re.search(r"start=inv_([\w-]+)", invite_msg.text)
    assert match
    return match.group(1)


async def events(container: Container, name: str) -> list[AnalyticsEventRow]:
    await container.dispatcher.dispatch_batch()
    async with container.db.sessions() as s:
        rows = await s.scalars(
            select(AnalyticsEventRow).where(AnalyticsEventRow.name == name).order_by(AnalyticsEventRow.occurred_at)
        )
        return list(rows.all())


async def test_acceptor_joins_leader_family_and_gets_a_magic_link(
    client: httpx.AsyncClient, container: Container
) -> None:
    token = await register_leader(client)
    reply = texts(await send(client, message_update(f"/start inv_{token}", tg_user_id=ACCEPTOR, first_name="Мама")))
    assert len(reply) == 1
    assert reply[0].startswith("Ты получил приглашение в пространство семьи «Семья Лидер». Переходи — ")
    magic = re.search(r"/auth/tg\?token=([\w-]+)", reply[0])
    assert magic

    login = await client.post("/v1/auth/magic", json={"token": magic.group(1)}, headers=PWA)
    me = (await client.get("/v1/me", headers={**PWA, "Authorization": f"Bearer {login.json()['access_token']}"})).json()
    assert [(f["name"], f["role"]) for f in me["families"]] == [("Семья Лидер", "adult")]
    assert me["active_family_id"] == me["families"][0]["id"]
    assert me["onboarding_completed"] is False  # acceptor also goes through screen C

    async with container.db.sessions() as s:
        assert len((await s.scalars(select(MemberRow))).all()) == 2  # no family was created for the acceptor
        leader = (await s.scalars(select(UserRow).where(UserRow.first_name == "Лидер"))).one()
        invite = (await s.scalars(select(InviteRow))).one()
    assert invite.uses == 1

    [signup] = [e for e in await events(container, "user_signed_up") if e.properties["acquisition_source"] == "invite"]
    assert signup.properties["invite_id"] == str(invite.id)
    assert signup.properties["referrer_user_id"] == str(leader.id)
    [opened] = await events(container, "invite_opened")
    assert opened.properties == {"invite_id": str(invite.id), "is_new_user": True, "result": "accepted"}
    [accepted] = await events(container, "invite_accepted")
    assert accepted.properties["member_role"] == "adult"
    assert opened.occurred_at <= accepted.occurred_at  # funnel order


async def test_opening_the_invite_again_says_already_member(client: httpx.AsyncClient, container: Container) -> None:
    token = await register_leader(client)
    await send(client, message_update(f"/start inv_{token}", tg_user_id=ACCEPTOR))
    again = texts(await send(client, message_update(f"/start inv_{token}", tg_user_id=ACCEPTOR)))
    assert again[0].startswith("Ты уже в семье «Семья Лидер»")
    assert [e.properties["result"] for e in await events(container, "invite_opened")] == ["accepted", "already_member"]
    assert len(await events(container, "invite_accepted")) == 1


async def test_leader_opening_own_invite_is_already_member(client: httpx.AsyncClient) -> None:
    token = await register_leader(client)
    reply = texts(await send(client, message_update(f"/start inv_{token}", tg_user_id=LEADER)))
    assert reply[0].startswith("Ты уже в семье")


async def test_dead_invite_creates_no_account_and_offers_own_family(
    client: httpx.AsyncClient, container: Container
) -> None:
    sent = await send(client, message_update("/start inv_nope", tg_user_id=ACCEPTOR))
    assert texts(sent)[0].startswith("Это приглашение недействительно")
    async with container.db.sessions() as s:
        assert (await s.scalars(select(UserRow))).all() == []
    [opened] = await events(container, "invite_opened")
    assert opened.properties == {"invite_id": None, "is_new_user": True, "result": "invalid"}

    # "Создать своё пространство" → the normal leader registration (screen E)
    sent = await send(client, callback_update("register_own", tg_user_id=ACCEPTOR, first_name="Мама"))
    assert texts(sent)[0] == "<b>Пространство семьи зарегистрировано!</b>"


async def test_revoked_invite_is_expired(client: httpx.AsyncClient, container: Container) -> None:
    token = await register_leader(client)
    async with container.db.transaction() as s:
        invite = (await s.scalars(select(InviteRow))).one()
        invite.revoked_at = invite.created_at
    sent = await send(client, message_update(f"/start inv_{token}", tg_user_id=ACCEPTOR))
    assert texts(sent)[0].startswith("Это приглашение недействительно")
    [opened] = await events(container, "invite_opened")
    assert opened.properties["result"] == "expired"


async def test_leader_of_own_family_can_join_another_and_switch(client: httpx.AsyncClient) -> None:
    token = await register_leader(client)
    own = texts(await send(client, message_update("/start", tg_user_id=ACCEPTOR, first_name="Мама")))
    assert own[0] == "<b>Пространство семьи зарегистрировано!</b>"
    joined = texts(await send(client, message_update(f"/start inv_{token}", tg_user_id=ACCEPTOR, first_name="Мама")))
    magic = re.search(r"/auth/tg\?token=([\w-]+)", joined[0])
    assert magic
    login = await client.post("/v1/auth/magic", json={"token": magic.group(1)}, headers=PWA)
    auth = {**PWA, "Authorization": f"Bearer {login.json()['access_token']}"}

    me = (await client.get("/v1/me", headers=auth)).json()
    by_name = {f["name"]: f for f in me["families"]}
    assert set(by_name) == {"Семья Мама", "Семья Лидер"}
    assert me["active_family_id"] == by_name["Семья Лидер"]["id"]  # the one they just joined

    switched = await client.put("/v1/me/active-family", json={"family_id": by_name["Семья Мама"]["id"]}, headers=auth)
    assert switched.status_code == 200 and switched.json()["active_family_id"] == by_name["Семья Мама"]["id"]
    forbidden = await client.put("/v1/me/active-family", json={"family_id": str(uuid.uuid4())}, headers=auth)
    assert forbidden.status_code == 403

    # a plain /start later keeps using the active family, no third family appears
    later = texts(await send(client, message_update("/start", tg_user_id=ACCEPTOR, first_name="Мама")))
    assert later[0].startswith("Вы вошли")


async def test_invite_command_resends_with_share_button(client: httpx.AsyncClient) -> None:
    token = await register_leader(client)
    [msg] = [m for m in await send(client, message_update("/invite", tg_user_id=LEADER)) if isinstance(m, SendMessage)]
    assert f"inv_{token}" in msg.text and msg.reply_markup is not None
    unknown = texts(await send(client, message_update("/invite", tg_user_id=999)))
    assert unknown[0].startswith("Сначала зарегистрируйте семью")


async def test_inline_share_returns_invite_card_and_tracks_choice(
    client: httpx.AsyncClient, container: Container
) -> None:
    token = await register_leader(client)
    [answer] = await send(client, inline_query_update("invite", tg_user_id=LEADER))
    assert isinstance(answer, AnswerInlineQuery)
    [card] = answer.results
    assert card.title == "Пригласить в «Семья Лидер»"  # type: ignore[union-attr]
    assert f"inv_{token}" in card.input_message_content.message_text  # type: ignore[union-attr]
    assert answer.is_personal is True and answer.cache_time == 0

    await send(client, chosen_inline_update(card.id, tg_user_id=LEADER))
    [shared] = await events(container, "invite_shared")
    assert shared.properties == {"invite_id": card.id}


async def test_inline_share_for_unknown_user_points_to_registration(client: httpx.AsyncClient) -> None:
    [answer] = await send(client, inline_query_update("invite", tg_user_id=555))
    assert isinstance(answer, AnswerInlineQuery)
    assert answer.results == [] and answer.button is not None and answer.button.start_parameter == "from_inline"
