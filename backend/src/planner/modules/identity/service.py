"""Identity commands: Telegram users, PWA login handshake, magic links, sessions (ADR 0002)."""

import uuid
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any

import jwt
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from planner.application.principal import Principal
from planner.domain.identity import (
    HandshakeAlreadyUsed,
    HandshakeError,
    HandshakeExpired,
    HandshakeStatus,
    LoginHandshake,
    hash_token,
    new_token,
)
from planner.infra.db import Database
from planner.infra.ids import new_id
from planner.modules.analytics.catalog import (
    LoginHandshakeCompleted,
    LoginHandshakeStarted,
    MagicLinkRedeemed,
    MagicLinkRejected,
    Platform,
    UserSignedUp,
)
from planner.modules.analytics.tracker import EventContext, Tracker
from planner.modules.identity.tables import IdentityRow, LoginHandshakeRow, MagicTokenRow, SessionRow, UserRow

JWT_ALG = "HS256"
UTM_KEYS = ("utm_source", "utm_medium", "utm_campaign")


@dataclass(frozen=True, slots=True)
class AuthConfig:
    jwt_secret: str
    access_ttl: timedelta
    refresh_ttl: timedelta
    handshake_ttl: timedelta
    magic_ttl: timedelta
    app_version: str


@dataclass(frozen=True, slots=True)
class TelegramProfile:
    tg_user_id: int
    first_name: str
    username: str | None = None
    language_code: str | None = None


@dataclass(frozen=True, slots=True)
class SignupSource:
    """Where a new user came from; becomes the `user_signed_up` properties."""

    platform: Platform
    anonymous_id: uuid.UUID | None = None
    utm: dict[str, str] | None = None
    invite_id: uuid.UUID | None = None
    referrer_user_id: uuid.UUID | None = None


@dataclass(frozen=True, slots=True)
class StartedHandshake:
    handshake_id: uuid.UUID
    nonce: str
    expires_at: datetime


@dataclass(frozen=True, slots=True)
class AuthTokens:
    access_token: str
    expires_in: int
    refresh_token: str
    refresh_expires_at: datetime
    user_id: uuid.UUID


class AuthError(Exception):
    def __init__(self, reason: str) -> None:
        super().__init__(reason)
        self.reason = reason


def _now() -> datetime:
    return datetime.now(UTC)


class IdentityService:
    def __init__(self, db: Database, tracker: Tracker, config: AuthConfig) -> None:
        self._db = db
        self._tracker = tracker
        self._cfg = config

    # --Telegram users
    async def find_telegram_user(self, session: AsyncSession, tg_user_id: int) -> UserRow | None:
        return await session.scalar(
            select(UserRow)
            .join(IdentityRow, IdentityRow.user_id == UserRow.id)
            .where(IdentityRow.provider == "telegram", IdentityRow.subject == str(tg_user_id))
        )

    async def resolve_telegram(self, tg_user_id: int) -> tuple[uuid.UUID | None, uuid.UUID | None]:
        """Telegram id → (user id, active family id), for bot activity tracking."""
        async with self._db.sessions() as session:
            row = (
                await session.execute(
                    select(UserRow.id, UserRow.active_family_id)
                    .join(IdentityRow, IdentityRow.user_id == UserRow.id)
                    .where(IdentityRow.provider == "telegram", IdentityRow.subject == str(tg_user_id))
                )
            ).first()
        return (row.id, row.active_family_id) if row else (None, None)

    async def ensure_telegram_user(
        self, session: AsyncSession, profile: TelegramProfile, source: SignupSource, *, is_test: bool = False
    ) -> tuple[UserRow, bool]:
        """Find or create the user behind a Telegram account. Emits `user_signed_up` only on creation."""
        user = await self.find_telegram_user(session, profile.tg_user_id)
        if user is not None:
            return user, False
        user = UserRow(
            id=new_id(),
            first_name=profile.first_name[:128] or "—",
            locale=(profile.language_code or "ru")[:8],
            is_test=is_test,
        )
        session.add(user)
        await session.flush()
        session.add(
            IdentityRow(
                id=new_id(),
                user_id=user.id,
                provider="telegram",
                subject=str(profile.tg_user_id),
                username=profile.username,
            )
        )
        utm = source.utm or {}
        acquisition = "invite" if source.invite_id else ("utm" if utm else "organic")
        self._tracker.track(
            session,
            UserSignedUp(
                platform="pwa" if source.platform == Platform.PWA else "telegram_bot",
                acquisition_source=acquisition,
                invite_id=source.invite_id,
                referrer_user_id=source.referrer_user_id,
                locale=user.locale,
                **{k: utm.get(k) for k in UTM_KEYS},
            ),
            self._ctx(Platform.TELEGRAM_BOT, user.id, anonymous_id=source.anonymous_id),
        )
        return user, True

    async def lock_user(self, session: AsyncSession, user_id: uuid.UUID) -> UserRow:
        """Serializes per-user commands (e.g. two quick /start presses must not create two families)."""
        user = await session.scalar(select(UserRow).where(UserRow.id == user_id).with_for_update())
        assert user is not None
        return user

    # --PWA ↔ bot handshake
    async def start_handshake(
        self,
        *,
        challenge: str,
        platform: Platform,
        anonymous_id: uuid.UUID | None,
        utm: dict[str, str] | None,
    ) -> StartedHandshake:
        utm = {k: v[:200] for k, v in (utm or {}).items() if k in UTM_KEYS}
        row = LoginHandshakeRow(
            id=new_id(),
            nonce=new_token(),
            challenge=challenge,
            status=HandshakeStatus.PENDING.value,
            anonymous_id=anonymous_id,
            platform=platform.value,
            utm=utm,
            expires_at=_now() + self._cfg.handshake_ttl,
        )
        async with self._db.transaction() as session:
            session.add(row)
            self._tracker.track(
                session,
                LoginHandshakeStarted(handshake_id=row.id, **{k: utm.get(k) for k in UTM_KEYS}),
                self._ctx(platform, None, anonymous_id=anonymous_id),
            )
        return StartedHandshake(row.id, row.nonce, row.expires_at)

    async def get_handshake_for_bind(self, session: AsyncSession, nonce: str) -> LoginHandshakeRow | None:
        return await session.scalar(select(LoginHandshakeRow).where(LoginHandshakeRow.nonce == nonce).with_for_update())

    def signup_source(self, row: LoginHandshakeRow | None) -> SignupSource:
        if row is None:
            return SignupSource(platform=Platform.TELEGRAM_BOT)
        return SignupSource(platform=Platform(row.platform), anonymous_id=row.anonymous_id, utm=row.utm or None)

    def bind_handshake(self, row: LoginHandshakeRow, user_id: uuid.UUID, *, is_new_user: bool) -> None:
        """Raises HandshakeError when the nonce can't be bound (expired / taken)."""
        hs = self._domain(row)
        hs.bind(user_id, _now())
        if row.status != HandshakeStatus.BOUND.value:
            row.bound_at = _now()
            row.is_new_user = is_new_user
        row.status, row.user_id = hs.status.value, user_id

    async def exchange_handshake(self, nonce: str, verifier: str, *, method: str = "poll") -> AuthTokens | None:
        """None while the user hasn't pressed Start yet. Raises AuthError when it can never succeed."""
        async with self._db.transaction() as session:
            row = await session.scalar(
                select(LoginHandshakeRow).where(LoginHandshakeRow.nonce == nonce).with_for_update()
            )
            if row is None:
                raise AuthError("invalid")
            hs = self._domain(row)
            try:
                ready = hs.can_exchange(verifier, _now())
            except HandshakeError as exc:
                raise AuthError(exc.reason) from exc
            if not ready:
                return None
            hs.consume()
            row.status, row.consumed_at = hs.status.value, _now()
            assert row.user_id is not None
            platform = Platform(row.platform)
            tokens = await self._create_session(session, row.user_id, platform, method)
            self._tracker.track(
                session,
                LoginHandshakeCompleted(handshake_id=row.id, is_new_user=bool(row.is_new_user), method=method),  # type: ignore[arg-type]
                self._ctx(platform, row.user_id, anonymous_id=row.anonymous_id),
            )
            return tokens

    # --magic links
    async def issue_magic_token(self, session: AsyncSession, user_id: uuid.UUID) -> str:
        token = new_token(32)
        session.add(
            MagicTokenRow(
                id=new_id(),
                token_hash=hash_token(token),
                user_id=user_id,
                expires_at=_now() + self._cfg.magic_ttl,
            )
        )
        return token

    async def redeem_magic_token(self, token: str, *, platform: Platform, anonymous_id: uuid.UUID | None) -> AuthTokens:
        reason: str | None = None
        async with self._db.transaction() as session:
            row = await session.scalar(
                select(MagicTokenRow).where(MagicTokenRow.token_hash == hash_token(token)).with_for_update()
            )
            if row is None:
                reason = "invalid"
            elif row.used_at is not None:
                reason = "used"
            elif _now() >= row.expires_at:
                reason = "expired"
            if row is None or reason is not None:
                # The rejection is recorded (committed); the error is raised after the transaction.
                self._tracker.track(
                    session,
                    MagicLinkRejected(reason=reason),  # type: ignore[arg-type]
                    self._ctx(platform, row.user_id if row else None, anonymous_id),
                )
            else:
                row.used_at = _now()
                tokens = await self._create_session(session, row.user_id, platform, "magic_link")
                self._tracker.track(session, MagicLinkRedeemed(), self._ctx(platform, row.user_id, anonymous_id))
                return tokens
        raise AuthError(reason or "invalid")

    # --sessions
    async def refresh(self, refresh_token: str) -> AuthTokens:
        async with self._db.transaction() as session:
            row = await session.scalar(
                select(SessionRow).where(SessionRow.refresh_hash == hash_token(refresh_token)).with_for_update()
            )
            if row is None:
                raise AuthError("invalid")
            if _now() >= row.expires_at:
                raise AuthError("expired")
            if row.revoked_at is None and row.rotated_at is None:
                row.rotated_at = _now()
                return await self._create_session(
                    session, row.user_id, Platform(row.platform), row.login_method, chain_id=row.chain_id
                )
            # A rotated/revoked token came back: likely stolen. Kill the whole login chain (committed).
            await session.execute(
                update(SessionRow)
                .where(SessionRow.chain_id == row.chain_id, SessionRow.revoked_at.is_(None))
                .values(revoked_at=_now())
            )
        raise AuthError("reused")

    async def logout(self, refresh_token: str) -> None:
        async with self._db.transaction() as session:
            row = await session.scalar(select(SessionRow).where(SessionRow.refresh_hash == hash_token(refresh_token)))
            if row is not None:
                await session.execute(
                    update(SessionRow)
                    .where(SessionRow.chain_id == row.chain_id, SessionRow.revoked_at.is_(None))
                    .values(revoked_at=_now())
                )

    def decode_access(self, token: str) -> Principal:
        try:
            claims = jwt.decode(token, self._cfg.jwt_secret, algorithms=[JWT_ALG], options={"require": ["exp", "sub"]})
        except jwt.PyJWTError as exc:
            raise AuthError("invalid_token") from exc
        if claims.get("typ") != "access":
            raise AuthError("invalid_token")
        fid = claims.get("fid")
        sid = claims.get("sid")
        return Principal(
            user_id=uuid.UUID(claims["sub"]),
            family_id=uuid.UUID(fid) if fid else None,
            session_chain_id=uuid.UUID(sid) if sid else None,
        )

    async def _create_session(
        self,
        session: AsyncSession,
        user_id: uuid.UUID,
        platform: Platform,
        method: str,
        *,
        chain_id: uuid.UUID | None = None,
    ) -> AuthTokens:
        user = await session.get(UserRow, user_id)
        assert user is not None
        refresh = new_token(32)
        now = _now()
        chain = chain_id or new_id()
        session.add(
            SessionRow(
                id=new_id(),
                user_id=user_id,
                refresh_hash=hash_token(refresh),
                chain_id=chain,
                platform=platform.value,
                login_method=method,
                expires_at=now + self._cfg.refresh_ttl,
            )
        )
        claims: dict[str, Any] = {
            "typ": "access",
            "sub": str(user_id),
            "fid": str(user.active_family_id) if user.active_family_id else None,
            "sid": str(chain),
            "iat": int(now.timestamp()),
            "exp": int((now + self._cfg.access_ttl).timestamp()),
        }
        return AuthTokens(
            access_token=jwt.encode(claims, self._cfg.jwt_secret, algorithm=JWT_ALG),
            expires_in=int(self._cfg.access_ttl.total_seconds()),
            refresh_token=refresh,
            refresh_expires_at=now + self._cfg.refresh_ttl,
            user_id=user_id,
        )

    @staticmethod
    def _domain(row: LoginHandshakeRow) -> LoginHandshake:
        return LoginHandshake(
            nonce=row.nonce,
            challenge=row.challenge,
            status=HandshakeStatus(row.status),
            expires_at=row.expires_at,
            user_id=row.user_id,
        )

    def _ctx(
        self, platform: Platform, user_id: uuid.UUID | None, anonymous_id: uuid.UUID | None = None
    ) -> EventContext:
        return EventContext(
            platform=platform, user_id=user_id, anonymous_id=anonymous_id, app_version=self._cfg.app_version
        )


__all__ = [
    "AuthConfig",
    "AuthError",
    "AuthTokens",
    "HandshakeAlreadyUsed",
    "HandshakeExpired",
    "IdentityService",
    "SignupSource",
    "StartedHandshake",
    "TelegramProfile",
]
