import json
import uuid
from datetime import UTC, datetime, timedelta

import httpx
from sqlalchemy import select

from planner.bootstrap import Container
from planner.modules.analytics.tables import AnalyticsEventRow
from planner.modules.assistant.llm_gateway.fake import FakeProvider
from planner.modules.assistant.llm_gateway.port import Image, LLMBudgetExceeded, LLMRequest
from planner.modules.assistant.tables import DraftActionRow
from planner.modules.planning.tables import EventRow, TaskRow


def llm_returns(fake: FakeProvider, *answers: dict | str) -> None:
    queue = [a if isinstance(a, str) else json.dumps(a, ensure_ascii=False) for a in answers]

    def respond(_: LLMRequest) -> str:
        return queue.pop(0) if len(queue) > 1 else queue[0]

    fake._responder = respond


async def family(client: httpx.AsyncClient, tg_user_id: int = 51) -> tuple[uuid.UUID, uuid.UUID]:
    r = (await client.post("/v1/test/bot-start", json={"tg_user_id": tg_user_id, "first_name": "Дима"})).json()
    s = await client.post("/v1/auth/magic", json={"token": r["magic_token"]}, headers={"X-Client-Platform": "pwa"})
    me = (await client.get("/v1/me", headers={"Authorization": f"Bearer {s.json()['access_token']}"})).json()
    return uuid.UUID(me["user"]["id"]), uuid.UUID(me["active_family_id"])


async def names(container: Container) -> list[str]:
    await container.dispatcher.dispatch_batch()
    async with container.db.sessions() as s:
        return [e.name for e in (await s.scalars(select(AnalyticsEventRow).order_by(AnalyticsEventRow.occurred_at)))]


async def test_capture_confirm_creates_event(
    client: httpx.AsyncClient, container: Container, fake_llm: FakeProvider
) -> None:
    user_id, family_id = await family(client)
    llm_returns(
        fake_llm,
        {"items": [{"kind": "event", "title": "Танцы у Даши", "date": None, "time": "13:00", "people": ["Даша"]}]},
    )
    out = await container.capture.capture(
        user_id=user_id,
        family_id=family_id,
        text="в 13:00 у дашки танцы забудь дим",
        source="forwarded",
        written_at=datetime.now(UTC),
    )
    assert out.failure is None
    [draft] = out.drafts
    assert draft.summary.startswith("Событие: Танцы у Даши · ") and not draft.raw
    assert "<message>" in fake_llm.calls[0].messages[1].content  # untrusted text is fenced

    assert (await container.capture.confirm(draft.id, user_id)).status == "done"
    assert (await container.capture.confirm(draft.id, user_id)).status == "already"  # double tap
    async with container.db.sessions() as s:
        event = (await s.scalars(select(EventRow))).one()
    assert (event.title, event.created_via, event.source_text) == (
        "Танцы у Даши",
        "bot_draft",
        "в 13:00 у дашки танцы забудь дим",
    )
    got = await names(container)
    for name in ("capture_received", "draft_action_created", "event_created", "draft_action_confirmed"):
        assert got.count(name) == 1, name


async def test_llm_failure_offers_saving_as_is(
    client: httpx.AsyncClient, container: Container, fake_llm: FakeProvider
) -> None:
    user_id, family_id = await family(client)
    fake_llm.fail_with = LLMBudgetExceeded("Budget has been exceeded")
    out = await container.capture.capture(
        user_id=user_id,
        family_id=family_id,
        text="забрать посылку до 26.09\nи ещё",
        source="own",
        written_at=datetime.now(UTC),
    )
    assert out.failure == "llm_budget"
    [draft] = out.drafts
    assert draft.raw and draft.summary == "Задача: забрать посылку до 26.09"
    await container.capture.confirm(draft.id, user_id)
    async with container.db.sessions() as s:
        assert (await s.scalars(select(TaskRow))).one().created_via == "bot_raw"
    assert "capture_failed" in await names(container)


async def test_photo_capture_is_counted_and_has_no_raw_fallback(
    client: httpx.AsyncClient, container: Container, fake_llm: FakeProvider
) -> None:
    user_id, family_id = await family(client)
    photo = Image(b"jpeg", "image/jpeg")
    fake_llm.fail_with = LLMBudgetExceeded("Budget has been exceeded")
    out = await container.capture.capture(
        user_id=user_id, family_id=family_id, text="", images=(photo,), source="own", written_at=datetime.now(UTC)
    )
    assert (out.failure, out.drafts) == ("llm_budget", [])

    fake_llm.fail_with = None
    llm_returns(fake_llm, {"items": [{"kind": "task", "title": "Купить краски"}]})
    out = await container.capture.capture(
        user_id=user_id, family_id=family_id, text="", images=(photo,), source="own", written_at=datetime.now(UTC)
    )
    [draft] = out.drafts
    assert (draft.summary, draft.raw) == ("Задача: Купить краски", False)
    assert fake_llm.calls[-1].messages[1].images == (photo,)

    await container.dispatcher.dispatch_batch()
    async with container.db.sessions() as s:
        received = (
            await s.scalars(select(AnalyticsEventRow).where(AnalyticsEventRow.name == "capture_received"))
        ).all()
    assert [e.properties["content_type"] for e in received] == ["photo", "photo"]


async def test_invalid_json_is_retried_once_then_falls_back(
    client: httpx.AsyncClient, container: Container, fake_llm: FakeProvider
) -> None:
    user_id, family_id = await family(client)
    llm_returns(fake_llm, "oops", {"items": [{"kind": "task", "title": "Купить молоко"}]})
    out = await container.capture.capture(
        user_id=user_id, family_id=family_id, text="молоко", source="own", written_at=datetime.now(UTC)
    )
    assert [d.summary for d in out.drafts] == ["Задача: Купить молоко"] and len(fake_llm.calls) == 2

    llm_returns(fake_llm, "still not json")
    fake_llm.calls.clear()
    out = await container.capture.capture(
        user_id=user_id, family_id=family_id, text="хм", source="own", written_at=datetime.now(UTC)
    )
    assert out.failure == "invalid_output" and out.drafts[0].raw and len(fake_llm.calls) == 2


async def test_nothing_to_plan_is_no_items(
    client: httpx.AsyncClient, container: Container, fake_llm: FakeProvider
) -> None:
    user_id, family_id = await family(client)
    llm_returns(fake_llm, {"items": []})
    out = await container.capture.capture(
        user_id=user_id, family_id=family_id, text="привет!", source="own", written_at=datetime.now(UTC)
    )
    assert out.failure == "no_items" and out.drafts[0].raw


async def test_revise_replaces_draft_and_cancel_and_expiry(
    client: httpx.AsyncClient, container: Container, fake_llm: FakeProvider
) -> None:
    user_id, family_id = await family(client)
    llm_returns(fake_llm, {"items": [{"kind": "task", "title": "Забрать посылку", "date": "2026-09-26"}]})
    [first] = (
        await container.capture.capture(
            user_id=user_id, family_id=family_id, text="посылка до 26.09", source="own", written_at=datetime.now(UTC)
        )
    ).drafts
    llm_returns(fake_llm, {"items": [{"kind": "task", "title": "Забрать посылку", "date": "2026-09-27"}]})
    revised = await container.capture.revise(first.id, user_id, "не 26, а 27")
    assert revised is not None and revised.drafts[0].summary.startswith("Задача: Забрать посылку · до вс 27.09")
    assert (await container.capture.confirm(first.id, user_id)).status == "gone"  # the old card is dead

    other_user = uuid.uuid4()
    second = revised.drafts[0]
    assert (await container.capture.confirm(second.id, other_user)).status == "gone"  # not yours
    assert (await container.capture.cancel(second.id, user_id)).status == "done"

    [third] = (
        await container.capture.capture(
            user_id=user_id, family_id=family_id, text="ещё", source="own", written_at=datetime.now(UTC)
        )
    ).drafts
    assert await container.capture.expire(datetime.now(UTC) + timedelta(hours=25)) == 1
    assert (await container.capture.confirm(third.id, user_id)).status == "gone"
    async with container.db.sessions() as s:
        statuses = {r.status for r in (await s.scalars(select(DraftActionRow))).all()}
    assert statuses == {"revised", "cancelled", "expired"}
    got = await names(container)
    assert got.count("draft_action_revised") == 1 and got.count("draft_action_expired") == 1
    assert got.count("capture_received") == 2  # revisions aren't new captures
