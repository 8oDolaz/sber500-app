import uuid
from datetime import UTC, datetime

import httpx
from sqlalchemy import select

from planner.bootstrap import Container
from planner.modules.analytics.tables import AnalyticsEventRow
from planner.settings import Settings


def ev(name: str, **props) -> dict:
    return {"id": str(uuid.uuid4()), "name": name, "occurred_at": datetime.now(UTC).isoformat(), "properties": props}


async def test_readyz(client: httpx.AsyncClient) -> None:
    r = await client.get("/readyz")
    assert r.status_code == 200
    body = r.json()
    assert body["ok"] and body["database"] and body["redis"]
    assert body["llm_models"] == {"ok": True, "provider": "fake", "missing": [], "error": None}


async def test_metrics_exposes_http_counters(client: httpx.AsyncClient) -> None:
    await client.get("/healthz")
    text = (await client.get("/metrics")).text
    assert 'http_requests_total{method="GET",route="/healthz",status="200"}' in text


async def test_preauth_ingest_accepts_funnel_events_only(client: httpx.AsyncClient, container: Container) -> None:
    anon = str(uuid.uuid4())
    events = [
        ev("screen_viewed", screen="welcome"),
        ev("register_clicked"),
        ev("how_to_clicked"),
        ev("nope"),
        ev("llm_budget_exceeded", scope="program", model="m", feature="f"),
        ev("screen_viewed", screen="bogus"),
    ]
    r = await client.post(
        "/v1/analytics/events",
        json={"anonymous_id": anon, "app_version": "0.1.0", "events": events},
        headers={"X-Client-Platform": "pwa", "X-Display-Mode": "standalone"},
    )
    assert r.status_code == 200
    body = r.json()
    assert body["accepted"] == 2
    assert sorted(x["reason"] for x in body["rejected"]) == [
        "auth_required",
        "invalid_properties",
        "server_only_event",
        "unknown_event",
    ]
    async with container.db.sessions() as s:
        rows = (await s.scalars(select(AnalyticsEventRow).order_by(AnalyticsEventRow.name))).all()
    assert [r.name for r in rows] == ["register_clicked", "screen_viewed"]
    assert all(str(r.anonymous_id) == anon and r.platform == "pwa" and r.user_id is None for r in rows)
    assert rows[1].properties == {"screen": "welcome", "display_mode": "standalone"}


async def test_ingest_rejects_unknown_platform(client: httpx.AsyncClient) -> None:
    r = await client.post(
        "/v1/analytics/events",
        json={"anonymous_id": str(uuid.uuid4()), "events": []},
        headers={"X-Client-Platform": "server"},
    )
    assert r.status_code == 400


async def test_preauth_ingest_is_rate_limited(client: httpx.AsyncClient, settings: Settings) -> None:
    batch = {
        "anonymous_id": str(uuid.uuid4()),
        "events": [ev("register_clicked") for _ in range(settings.analytics_preauth_rate_per_min)],
    }
    assert (await client.post("/v1/analytics/events", json=batch)).status_code == 200
    batch["events"] = [ev("register_clicked")]
    assert (await client.post("/v1/analytics/events", json=batch)).status_code == 429


async def test_telegram_webhook_requires_secret(client: httpx.AsyncClient) -> None:
    r = await client.post(
        "/webhooks/telegram", json={"update_id": 1}, headers={"X-Telegram-Bot-Api-Secret-Token": "wrong"}
    )
    assert r.status_code == 401
