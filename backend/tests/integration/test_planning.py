import uuid
from datetime import UTC, date, datetime, timedelta

import httpx
from sqlalchemy import select

from planner.bootstrap import Container
from planner.domain.planning import CreatedVia, NewEvent, NewTask
from planner.modules.analytics.catalog import Platform
from planner.modules.analytics.tables import AnalyticsEventRow
from planner.modules.planning.service import Actor

PWA = {"X-Client-Platform": "pwa"}


async def login(client: httpx.AsyncClient, tg_user_id: int) -> tuple[dict[str, str], str, str]:
    r = (await client.post("/v1/test/bot-start", json={"tg_user_id": tg_user_id})).json()
    s = await client.post("/v1/auth/magic", json={"token": r["magic_token"]}, headers=PWA)
    auth = {**PWA, "Authorization": f"Bearer {s.json()['access_token']}"}
    me = (await client.get("/v1/me", headers=auth)).json()
    return auth, me["active_family_id"], me["user"]["id"]


async def test_tasks_list_complete_and_undo(client: httpx.AsyncClient, container: Container) -> None:
    auth, family_id, user_id = await login(client, 21)
    actor = Actor(uuid.UUID(user_id), uuid.UUID(family_id), Platform.TELEGRAM_BOT)
    async with container.db.transaction() as s:
        later = await container.planning.create_task(s, actor, NewTask("без срока"), CreatedVia.BOT_RAW)
        soon = await container.planning.create_task(
            s, actor, NewTask("забрать посылку", due_date=date(2026, 9, 26)), CreatedVia.BOT_DRAFT
        )

    tasks = (await client.get(f"/v1/families/{family_id}/tasks", headers=auth)).json()
    assert [t["title"] for t in tasks] == ["забрать посылку", "без срока"]  # dated first

    done = await client.patch(f"/v1/families/{family_id}/tasks/{soon.id}", json={"done": True}, headers=auth)
    assert done.status_code == 200 and done.json()["done"] is True
    assert [t["id"] for t in (await client.get(f"/v1/families/{family_id}/tasks", headers=auth)).json()] == [
        str(later.id)
    ]
    undo = await client.patch(f"/v1/families/{family_id}/tasks/{soon.id}", json={"done": False}, headers=auth)
    assert undo.json()["done"] is False

    await container.dispatcher.dispatch_batch()
    async with container.db.sessions() as s:
        names = [e.name for e in (await s.scalars(select(AnalyticsEventRow))).all()]
    assert names.count("task_created") == 2 and names.count("task_completed") == 1


async def test_family_scope_is_enforced(client: httpx.AsyncClient, container: Container) -> None:
    _, family_a, user_a = await login(client, 31)
    auth_b, _, _ = await login(client, 32)
    async with container.db.transaction() as s:
        task = await container.planning.create_task(
            s, Actor(uuid.UUID(user_a), uuid.UUID(family_a), Platform.PWA), NewTask("секрет"), CreatedVia.UI
        )
    assert (await client.get(f"/v1/families/{family_a}/tasks", headers=auth_b)).status_code == 403
    assert (await client.get(f"/v1/families/{family_a}/events", headers=auth_b)).status_code == 403
    r = await client.patch(f"/v1/families/{family_a}/tasks/{task.id}", json={"done": True}, headers=auth_b)
    assert r.status_code == 403


async def test_upcoming_events_window_uses_family_timezone(client: httpx.AsyncClient, container: Container) -> None:
    auth, family_id, user_id = await login(client, 41)
    actor = Actor(uuid.UUID(user_id), uuid.UUID(family_id), Platform.TELEGRAM_BOT)
    now = datetime.now(UTC)
    async with container.db.transaction() as s:
        for title, event in [
            ("вчера", NewEvent("вчера", starts_at=now - timedelta(days=2))),
            ("скоро", NewEvent("скоро", starts_at=now + timedelta(minutes=1))),
            ("весь день", NewEvent("весь день", start_date=(now + timedelta(days=1)).date())),
            ("через месяц", NewEvent("через месяц", starts_at=now + timedelta(days=30))),
        ]:
            await container.planning.create_event(s, actor, event, CreatedVia.BOT_DRAFT, source_text=title)
    body = (await client.get(f"/v1/families/{family_id}/events", headers=auth)).json()
    assert body["timezone"] == "Europe/Moscow"
    # sorted by start; tomorrow's all-day event begins at local midnight, after "скоро"
    assert [e["title"] for e in body["events"]] == ["скоро", "весь день"]
