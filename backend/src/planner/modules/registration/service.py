"""The bot's `/start` use cases (SPEC flow, screens E and F).

- `/start login_<nonce>` (from the PWA's "Зарегистрироваться") and a plain `/start`:
  ensure the Telegram user → register their family space (+ invite) → bind the PWA handshake →
  issue a magic link back to the PWA.
- `/start inv_<token>` (the forwarded invite): ensure the user → join that family as an adult →
  magic link. An acceptor never gets a family of their own created implicitly.

Each runs in one transaction, serialized per user.
"""

import uuid
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Literal

from sqlalchemy import select

from planner.domain.families import INVITE_START_PREFIX, LOGIN_START_PREFIX, Role, invite_deep_link
from planner.domain.identity import HandshakeError
from planner.infra.db import Database
from planner.modules.analytics.catalog import InviteAccepted, InviteOpened, InviteShared, OnboardingCompleted, Platform
from planner.modules.analytics.tracker import EventContext, Tracker
from planner.modules.families.service import FamilyInvite, FamilyService
from planner.modules.families.tables import MemberRow
from planner.modules.identity.service import IdentityService, SignupSource, TelegramProfile


@dataclass(frozen=True, slots=True)
class StartResult:
    kind: Literal["family_registered", "logged_in", "invite_accepted", "invite_already_member", "invite_invalid"]
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
        tracker: Tracker,
        *,
        bot_username: str,
        public_app_url: str,
    ) -> None:
        self._db = db
        self._identity = identity
        self._families = families
        self._tracker = tracker
        self._bot_username = bot_username
        self._app_url = public_app_url.rstrip("/")

    async def handle_start(
        self, profile: TelegramProfile, payload: str | None, *, is_test: bool = False
    ) -> StartResult:
        payload = (payload or "").strip()
        if payload.startswith(INVITE_START_PREFIX):
            return await self._accept_invite(profile, payload.removeprefix(INVITE_START_PREFIX), is_test=is_test)
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
                magic_link=self._magic_link(token),
                magic_token=token,
                handshake_error=handshake_error,
                is_new_user=is_new,
            )

    async def _accept_invite(self, profile: TelegramProfile, token: str, *, is_test: bool) -> StartResult:
        async with self._db.transaction() as session:
            invite, status = await self._families.find_invite(session, token)
            existing = await self._identity.find_telegram_user(session, profile.tg_user_id)
            if status != "valid" or invite is None:
                # Don't create an account for a dead link; just record that it was opened.
                self._tracker.track(
                    session,
                    InviteOpened(invite_id=invite.id if invite else None, is_new_user=existing is None, result=status),  # type: ignore[arg-type]
                    EventContext(Platform.TELEGRAM_BOT, existing.id if existing else None),
                )
                return StartResult(kind="invite_invalid", user_id=existing.id if existing else None)

            source = SignupSource(
                platform=Platform.TELEGRAM_BOT, invite_id=invite.id, referrer_user_id=invite.created_by
            )
            user, is_new = await self._identity.ensure_telegram_user(session, profile, source, is_test=is_test)
            user = await self._identity.lock_user(session, user.id)
            outcome = await self._families.accept_invite(session, user, invite)
            ctx = EventContext(Platform.TELEGRAM_BOT, user.id, invite.family_id)
            self._tracker.track(session, InviteOpened(invite_id=invite.id, is_new_user=is_new, result=outcome), ctx)
            if outcome == "accepted":
                self._tracker.track(session, InviteAccepted(invite_id=invite.id, member_role=Role.ADULT.value), ctx)
            family = await self._families.get_family(session, invite.family_id)
            magic = await self._identity.issue_magic_token(session, user.id)
            return StartResult(
                kind="invite_accepted" if outcome == "accepted" else "invite_already_member",
                user_id=user.id,
                family_id=family.id,
                family_name=family.name,
                invite_link=invite_deep_link(self._bot_username, invite.token),
                magic_link=self._magic_link(magic),
                magic_token=magic,
                is_new_user=is_new,
            )

    async def invite_for_sharing(self, tg_user_id: int) -> FamilyInvite | None:
        """The active family's invite, for `/invite` and the inline "Поделиться" button."""
        async with self._db.transaction() as session:
            user = await self._identity.find_telegram_user(session, tg_user_id)
            if user is None:
                return None
            return await self._families.active_family_invite(session, user, Platform.TELEGRAM_BOT)

    def invite_link(self, invite_token: str) -> str:
        return invite_deep_link(self._bot_username, invite_token)

    async def record_invite_shared(self, tg_user_id: int, invite_id: uuid.UUID) -> None:
        async with self._db.transaction() as session:
            user = await self._identity.find_telegram_user(session, tg_user_id)
            self._tracker.track(
                session,
                InviteShared(invite_id=invite_id),
                EventContext(Platform.TELEGRAM_BOT, user.id if user else None, user.active_family_id if user else None),
            )

    async def switch_family(self, user_id: uuid.UUID, family_id: uuid.UUID) -> bool:
        async with self._db.transaction() as session:
            user = await self._identity.lock_user(session, user_id)
            return await self._families.set_active_family(session, user, family_id)

    def _magic_link(self, token: str) -> str:
        return f"{self._app_url}/auth/tg?token={token}"

    async def complete_onboarding(self, user_id: uuid.UUID, platform: Platform, app_version: str) -> None:
        """Screen C "В семью". Idempotent: the event is emitted only the first time."""
        async with self._db.transaction() as session:
            user = await self._identity.lock_user(session, user_id)
            if user.onboarding_completed_at is not None:
                return
            user.onboarding_completed_at = datetime.now(UTC)
            role = await session.scalar(
                select(MemberRow.role).where(MemberRow.user_id == user_id, MemberRow.family_id == user.active_family_id)
            )
            self._tracker.track(
                session,
                OnboardingCompleted(is_leader=role == Role.OWNER),
                EventContext(platform, user_id, user.active_family_id, app_version=app_version),
            )
