import httpx
from sqlalchemy import select

from planner.bootstrap import Container
from planner.modules.analytics.tables import AnalyticsEventRow

PWA = {"X-Client-Platform": "pwa"}


async def login(client: httpx.AsyncClient, tg_user_id: int = 11) -> dict[str, str]:
    r = await client.post("/v1/test/tg-handshake/nonce-x/bind", json={"tg_user_id": tg_user_id})
    s = await client.post("/v1/auth/magic", json={"token": r.json()["magic_token"]}, headers=PWA)
    return {**PWA, "Authorization": f"Bearer {s.json()['access_token']}"}


async def test_complete_onboarding_is_idempotent_and_tracked_once(
    client: httpx.AsyncClient, container: Container
) -> None:
    headers = await login(client)
    assert (await client.get("/v1/me", headers=headers)).json()["onboarding_completed"] is False

    first = await client.patch("/v1/me", json={"onboarding_completed": True}, headers=headers)
    again = await client.patch("/v1/me", json={"onboarding_completed": True}, headers=headers)
    assert first.status_code == again.status_code == 200
    assert first.json()["onboarding_completed"] is again.json()["onboarding_completed"] is True
    assert again.json()["bot_link"] == "https://t.me/kainem_test_bot"

    await container.dispatcher.dispatch_batch()
    async with container.db.sessions() as s:
        events = (
            await s.scalars(select(AnalyticsEventRow).where(AnalyticsEventRow.name == "onboarding_completed"))
        ).all()
    assert len(events) == 1
    assert events[0].properties == {"is_leader": True}
    assert events[0].platform == "pwa" and events[0].family_id is not None


async def test_onboarding_cannot_be_uncompleted(client: httpx.AsyncClient) -> None:
    headers = await login(client, 12)
    r = await client.patch("/v1/me", json={"onboarding_completed": False}, headers=headers)
    assert r.status_code == 422


async def test_patch_me_requires_auth(client: httpx.AsyncClient) -> None:
    assert (await client.patch("/v1/me", json={"onboarding_completed": True})).status_code == 401
