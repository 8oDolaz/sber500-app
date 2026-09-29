"""Leader registration through the bot (SPEC flow 1–3, screens E): the `/start` use case.

`/start login_<nonce>` (from the PWA's "Зарегистрироваться") and a plain `/start` both:
ensure the Telegram user → register their family space (+ invite) → bind the PWA handshake →
issue a magic link back to the PWA. One transaction, serialized per user.
"""

import uuid
from dataclasses import dataclass
from typing import Literal

from planner.domain.families import INVITE_START_PREFIX, LOGIN_START_PREFIX, invite_deep_link
from planner.domain.identity import HandshakeError
from planner.infra.db import Database
from planner.modules.analytics.catalog import Platform
from planner.modules.families.service import FamilyService
from planner.modules.identity.service import IdentityService, TelegramProfile


@dataclass(frozen=True, slots=True)
class StartResult:
    kind: Literal["family_registered", "logged_in", "invite_not_supported_yet"]
    user_id: uuid.UUID | None = None
    family_id: uuid.UUID | None = None
    family_name: str | None = None
    invite_link: str | None = None
    magic_link: str | None = None
    magic_token: str | None = None
    # Set when the PWA handshake in the payload could not be bound (expired / already used / unknown).
    handshake_error: str | None = None
    is_new_user: bool = False


class RegistrationService:
    def __init__(
        self,
        db: Database,
        identity: IdentityService,
        families: FamilyService,
        *,
        bot_username: str,
        public_app_url: str,
    ) -> None:
        self._db = db
        self._identity = identity
        self._families = families
        self._bot_username = bot_username
        self._app_url = public_app_url.rstrip("/")

    async def handle_start(
        self, profile: TelegramProfile, payload: str | None, *, is_test: bool = False
    ) -> StartResult:
        payload = (payload or "").strip()
        if payload.startswith(INVITE_START_PREFIX):
            return StartResult(kind="invite_not_supported_yet")  # acceptor flow arrives in M3
        nonce = payload.removeprefix(LOGIN_START_PREFIX) if payload.startswith(LOGIN_START_PREFIX) else None

        async with self._db.transaction() as session:
            handshake = await self._identity.get_handshake_for_bind(session, nonce) if nonce else None
            user, is_new = await self._identity.ensure_telegram_user(
                session, profile, self._identity.signup_source(handshake), is_test=is_test
            )
            user = await self._identity.lock_user(session, user.id)
            leader = await self._families.ensure_leader_family(session, user, Platform.TELEGRAM_BOT)

            handshake_error = None
            if nonce and handshake is None:
                handshake_error = "invalid"
            elif handshake is not None:
                try:
                    self._identity.bind_handshake(handshake, user.id, is_new_user=is_new)
                except HandshakeError as exc:
                    handshake_error = exc.reason

            token = await self._identity.issue_magic_token(session, user.id)
            return StartResult(
                kind="family_registered" if leader.created else "logged_in",
                user_id=user.id,
                family_id=leader.family.id,
                family_name=leader.family.name,
                invite_link=invite_deep_link(self._bot_username, leader.invite.token),
                magic_link=f"{self._app_url}/auth/tg?token={token}",
                magic_token=token,
                handshake_error=handshake_error,
                is_new_user=is_new,
            )
