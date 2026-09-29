"""M1 end to end: PWA handshake ↔ bot /start ↔ session, magic link, refresh rotation, analytics."""

import base64
import hashlib
import secrets
import uuid

import httpx
from sqlalchemy import select

from planner.bootstrap import Container
from planner.modules.analytics.tables import AnalyticsEventRow, UserActivityDaily
from planner.modules.families.tables import FamilyRow, InviteRow, MemberRow
from planner.modules.identity.tables import UserRow
from tests.integration.telegram import fake_bot, message_update

PWA = {"X-Client-Platform": "pwa", "X-Display-Mode": "standalone"}


def pkce() -> tuple[str, str]:
    verifier = secrets.token_urlsafe(48)
    challenge = base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest()).rstrip(b"=").decode()
    return verifier, challenge


async def start_handshake(client: httpx.AsyncClient, anon: uuid.UUID, **extra) -> tuple[str, str, dict]:
    verifier, challenge = pkce()
    r = await client.post(
        "/v1/auth/tg-handshake",
        json={"challenge": challenge, "anonymous_id": str(anon), **extra},
        headers=PWA,
    )
    assert r.status_code == 201, r.text
    return r.json()["nonce"], verifier, r.json()


async def press_start(client: httpx.AsyncClient, payload: str, tg_user_id: int = 42) -> list[str]:
    bot, session = fake_bot()
    await client.app.state.dispatcher.feed_update(  # type: ignore[attr-defined]
        bot, message_update(f"/start {payload}".strip(), tg_user_id=tg_user_id)
    )
    return session.texts()


async def refresh_call(client: httpx.AsyncClient, path: str, refresh_token: str) -> httpx.Response:
    client.cookies.clear()
    client.cookies.set("kn_refresh", refresh_token)
    return await client.post(path)


async def events(container: Container) -> list[AnalyticsEventRow]:
    await container.dispatcher.dispatch_batch()
    async with container.db.sessions() as s:
        return list((await s.scalars(select(AnalyticsEventRow).order_by(AnalyticsEventRow.received_at))).all())


async def test_leader_registers_through_bot_and_pwa_gets_a_session(
    client: httpx.AsyncClient, container: Container
) -> None:
    anon = uuid.uuid4()
    nonce, verifier, started = await start_handshake(client, anon, utm={"utm_source": "tg", "junk": "x"})
    assert started["deep_link"] == f"https://t.me/kainem_test_bot?start=login_{nonce}"

    exchange = f"/v1/auth/tg-handshake/{nonce}/exchange"
    assert (await client.post(exchange, json={"verifier": verifier})).status_code == 202  # not pressed yet

    texts = await press_start(client, f"login_{nonce}")
    assert texts[0] == "<b>Пространство семьи зарегистрировано!</b>"
    assert "?start=inv_" in texts[1] and "/auth/tg?token=" in texts[2]

    assert (await client.post(exchange, json={"verifier": pkce()[0]})).status_code == 403  # stolen nonce
    r = await client.post(exchange, json={"verifier": verifier})
    assert r.status_code == 200, r.text
    assert "kn_refresh" in r.cookies
    token = r.json()["access_token"]
    again = await client.post(exchange, json={"verifier": verifier})
    assert again.status_code == 410 and again.json()["detail"]["reason"] == "used"

    me = await client.get("/v1/me", headers={**PWA, "Authorization": f"Bearer {token}"})
    assert me.status_code == 200
    body = me.json()
    assert body["onboarding_completed"] is False
    assert [f["role"] for f in body["families"]] == ["owner"]
    assert body["families"][0]["name"] == "Семья Лидер"
    assert body["active_family_id"] == body["families"][0]["id"]

    async with container.db.sessions() as s:
        assert len((await s.scalars(select(FamilyRow))).all()) == 1
        assert len((await s.scalars(select(MemberRow))).all()) == 1
        assert len((await s.scalars(select(InviteRow))).all()) == 1
        activity = (await s.scalars(select(UserActivityDaily))).all()
    # the signup /start counts as bot activity, /v1/me as PWA activity
    assert {a.platform for a in activity} == {"pwa", "telegram_bot"}

    names = [e.name for e in await events(container)]
    assert names.count("user_signed_up") == 1
    for expected in ("login_handshake_started", "family_created", "invite_created", "login_handshake_completed"):
        assert expected in names
    signup = next(e for e in await events(container) if e.name == "user_signed_up")
    assert signup.anonymous_id == anon  # joins the pre-login funnel
    assert signup.properties["platform"] == "pwa"
    assert signup.properties["acquisition_source"] == "utm"
    assert signup.properties["utm_source"] == "tg"


async def test_expired_or_unknown_nonce_still_registers_and_sends_magic_link(client: httpx.AsyncClient) -> None:
    texts = await press_start(client, "login_doesnotexist")
    assert texts[0] == "<b>Пространство семьи зарегистрировано!</b>"
    assert len(texts) == 3


async def test_other_user_cannot_bind_someone_elses_nonce(client: httpx.AsyncClient) -> None:
    nonce, verifier, _ = await start_handshake(client, uuid.uuid4())
    await press_start(client, f"login_{nonce}", tg_user_id=1)
    texts = await press_start(client, f"login_{nonce}", tg_user_id=2)
    assert texts[0].startswith("Ссылка для входа устарела")
    r = await client.post(f"/v1/auth/tg-handshake/{nonce}/exchange", json={"verifier": verifier})
    me = await client.get("/v1/me", headers={"Authorization": f"Bearer {r.json()['access_token']}"})
    assert me.json()["user"]["first_name"] == "Лидер"
    async with client.app.state.container.db.sessions() as s:  # type: ignore[attr-defined]
        users = (await s.scalars(select(UserRow))).all()
    assert len(users) == 2  # the second person got their own account, not the first one's session


async def test_magic_link_is_single_use(client: httpx.AsyncClient, container: Container) -> None:
    r = await client.post(f"/v1/test/tg-handshake/{'n' * 10}/bind", json={"tg_user_id": 7})
    token = r.json()["magic_token"]
    ok = await client.post("/v1/auth/magic", json={"token": token}, headers=PWA)
    assert ok.status_code == 200 and ok.json()["access_token"]
    reused = await client.post("/v1/auth/magic", json={"token": token}, headers=PWA)
    assert reused.status_code == 410 and reused.json()["detail"]["reason"] == "used"
    names = [e.name for e in await events(container)]
    assert "magic_link_redeemed" in names and "magic_link_rejected" in names


async def test_refresh_rotates_and_reuse_revokes_the_chain(client: httpx.AsyncClient) -> None:
    r = await client.post(f"/v1/test/tg-handshake/{'n' * 10}/bind", json={"tg_user_id": 8})
    login = await client.post("/v1/auth/magic", json={"token": r.json()["magic_token"]}, headers=PWA)
    first_refresh = login.cookies["kn_refresh"]

    rotated = await refresh_call(client, "/v1/auth/refresh", first_refresh)
    assert rotated.status_code == 200
    second_refresh = rotated.cookies["kn_refresh"]
    assert second_refresh != first_refresh

    stolen = await refresh_call(client, "/v1/auth/refresh", first_refresh)
    assert stolen.status_code == 401 and stolen.json()["detail"]["reason"] == "reused"
    # the legitimate latest token is revoked too: the whole login must re-authenticate
    assert (await refresh_call(client, "/v1/auth/refresh", second_refresh)).status_code == 401


async def test_logout_revokes_refresh(client: httpx.AsyncClient) -> None:
    r = await client.post(f"/v1/test/tg-handshake/{'n' * 10}/bind", json={"tg_user_id": 9})
    login = await client.post("/v1/auth/magic", json={"token": r.json()["magic_token"]}, headers=PWA)
    refresh = login.cookies["kn_refresh"]
    assert (await refresh_call(client, "/v1/auth/logout", refresh)).status_code == 204
    assert (await refresh_call(client, "/v1/auth/refresh", refresh)).status_code == 401


async def test_bad_bearer_token_is_401_not_anonymous(client: httpx.AsyncClient) -> None:
    assert (await client.get("/v1/me", headers={"Authorization": "Bearer nope"})).status_code == 401
    assert (await client.get("/v1/me")).status_code == 401


async def test_test_users_are_flagged(client: httpx.AsyncClient, container: Container) -> None:
    await client.post(f"/v1/test/tg-handshake/{'n' * 10}/bind", json={"tg_user_id": 10})
    async with container.db.sessions() as s:
        assert (await s.scalars(select(UserRow))).one().is_test is True
