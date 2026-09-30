"""Load test: realistic kainem traffic through the public entry point (nginx → API → Postgres/Redis).

Two kinds of visitors:
- FamilyMember (signed in): opens the main screen, forwards messages to the bot and confirms the draft,
  ticks tasks, sends analytics batches, refreshes the session.
- Guest (not signed in): opens the welcome screen, sends pre-login analytics, starts a Telegram login.

The Telegram side (bot /start, forwarded messages, «Сохранить») goes through the test-only endpoints,
which call the same services as the bot handlers. The LLM is the fake provider: no budget is spent.
Every account is is_test and every analytics batch is tagged app_version=loadtest, so dashboards stay clean.

Target: ~10 RPS in total (see docs/load-test.md for how to run and the results).
"""

import base64
import hashlib
import os
import random
import secrets
import uuid
from datetime import UTC, datetime

from locust import HttpUser, between, constant_throughput, task

PWA = {"X-Client-Platform": "pwa", "X-Display-Mode": "standalone"}
# Actions per second per simulated user; tuned so the whole mix lands at ~10 requests/s.
MEMBER_ACTIONS_PER_SEC = float(os.getenv("MEMBER_ACTIONS_PER_SEC", "0.26"))

MESSAGES = [
    "в 13:00 у дашки танцы забудь дим",
    "забрать посылку до 26.09",
    "завтра в 9 утра стоматолог у Маши",
    "купить молоко и хлеб",
    "в пятницу родительское собрание в 18:30",
    "оплатить коммуналку до 10 числа",
]


def pkce_pair() -> tuple[str, str]:
    verifier = secrets.token_urlsafe(32)
    challenge = base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest()).rstrip(b"=").decode()
    return verifier, challenge


def event(name: str, **props: object) -> dict:
    return {"id": str(uuid.uuid4()), "name": name, "occurred_at": datetime.now(UTC).isoformat(), "properties": props}


class FamilyMember(HttpUser):
    weight = 4
    wait_time = constant_throughput(MEMBER_ACTIONS_PER_SEC)

    def on_start(self) -> None:
        self.tg_user_id = random.randint(10**11, 10**12)
        self.anonymous_id = str(uuid.uuid4())
        started = self.client.post(
            "/api/v1/test/bot-start",
            json={"tg_user_id": self.tg_user_id, "first_name": "Нагрузка"},
            name="setup: bot /start",
        ).json()
        self._accept(
            self.client.post(
                "/api/v1/auth/magic", json={"token": started["magic_token"]}, headers=PWA, name="setup: magic link"
            )
        )
        me = self.client.get("/api/v1/me", headers=self.auth, name="/v1/me").json()
        self.family_id = me["active_family_id"]
        self.client.patch("/api/v1/me", json={"onboarding_completed": True}, headers=self.auth, name="/v1/me [PATCH]")

    def _accept(self, response) -> None:
        self.auth = {**PWA, "Authorization": f"Bearer {response.json()['access_token']}"}

    @task(6)
    def open_main_screen(self) -> None:
        self.client.get("/api/v1/me", headers=self.auth, name="/v1/me")
        self.client.get(f"/api/v1/families/{self.family_id}/tasks", headers=self.auth, name="/v1/families/:id/tasks")
        self.client.get(f"/api/v1/families/{self.family_id}/events", headers=self.auth, name="/v1/families/:id/events")

    @task(2)
    def forward_to_bot_and_save(self) -> None:
        captured = self.client.post(
            "/api/v1/test/capture",
            json={"tg_user_id": self.tg_user_id, "text": random.choice(MESSAGES)},
            name="bot: forwarded message",
        ).json()
        for draft in captured.get("drafts", [])[:1]:
            self.client.post(
                f"/api/v1/test/drafts/{draft['id']}/confirm",
                json={"tg_user_id": self.tg_user_id},
                name="bot: «Сохранить»",
            )

    @task(1)
    def tick_a_task(self) -> None:
        tasks = self.client.get(
            f"/api/v1/families/{self.family_id}/tasks", headers=self.auth, name="/v1/families/:id/tasks"
        ).json()
        if tasks:
            self.client.patch(
                f"/api/v1/families/{self.family_id}/tasks/{tasks[0]['id']}",
                json={"done": True},
                headers=self.auth,
                name="/v1/families/:id/tasks/:id [PATCH]",
            )

    @task(2)
    def send_analytics(self) -> None:
        self.client.post(
            "/api/v1/analytics/events",
            json={
                "anonymous_id": self.anonymous_id,
                "app_version": "loadtest",
                "events": [event("screen_viewed", screen="home"), event("how_to_clicked")],
            },
            headers=self.auth,
            name="/v1/analytics/events",
        )

    @task(1)
    def refresh_session(self) -> None:
        with self.client.post("/api/v1/auth/refresh", headers=PWA, name="/v1/auth/refresh", catch_response=True) as r:
            if r.status_code == 200:
                self._accept(r)


class Guest(HttpUser):
    weight = 1
    wait_time = between(8, 12)

    def on_start(self) -> None:
        self.anonymous_id = str(uuid.uuid4())

    @task
    def welcome_and_start_login(self) -> None:
        self.client.get("/", name="PWA shell /")
        self.client.post(
            "/api/v1/analytics/events",
            json={
                "anonymous_id": self.anonymous_id,
                "app_version": "loadtest",
                "events": [event("screen_viewed", screen="welcome"), event("register_clicked")],
            },
            headers=PWA,
            name="/v1/analytics/events [pre-login]",
        )
        verifier, challenge = pkce_pair()
        started = self.client.post(
            "/api/v1/auth/tg-handshake",
            json={"challenge": challenge, "anonymous_id": self.anonymous_id},
            headers=PWA,
            name="/v1/auth/tg-handshake",
        ).json()
        # One poll: the user hasn't pressed Start, so 202 is the expected answer.
        with self.client.post(
            f"/api/v1/auth/tg-handshake/{started['nonce']}/exchange",
            json={"verifier": verifier},
            headers=PWA,
            name="/v1/auth/tg-handshake/:nonce/exchange",
            catch_response=True,
        ) as r:
            if r.status_code == 202:
                r.success()
