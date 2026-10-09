"""Identity rules (ADR 0002). Pure: no I/O, no frameworks."""

import base64
import hashlib
import hmac
import secrets
from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum


class HandshakeStatus(StrEnum):
    PENDING = "pending"  # created by the PWA, waiting for /start in the bot
    BOUND = "bound"  # the bot tied it to a Telegram user; the PWA may exchange it once
    CONSUMED = "consumed"  # exchanged for a session


class HandshakeError(Exception):
    """Base for handshake failures; `reason` is stable and shown to analytics/clients."""

    reason = "invalid"


class HandshakeExpired(HandshakeError):
    reason = "expired"


class HandshakeAlreadyUsed(HandshakeError):
    reason = "used"


class VerifierMismatch(HandshakeError):
    reason = "verifier_mismatch"


def new_token(nbytes: int = 24) -> str:
    """URL-safe random token. 24 bytes → 32 chars, fits Telegram's 64-char /start payload with a prefix."""
    return secrets.token_urlsafe(nbytes)


def hash_token(token: str) -> str:
    """Tokens are stored hashed: a DB leak must not yield usable links or sessions."""
    return hashlib.sha256(token.encode()).hexdigest()


def pkce_challenge(verifier: str) -> str:
    """S256 challenge, as in RFC 7636: base64url(sha256(verifier)) without padding."""
    digest = hashlib.sha256(verifier.encode()).digest()
    return base64.urlsafe_b64encode(digest).rstrip(b"=").decode()


@dataclass
class LoginHandshake:
    """PWA ↔ bot login. The nonce travels through a public t.me URL, so claiming the session
    also requires the PKCE verifier that never left the PWA."""

    nonce: str
    challenge: str
    status: HandshakeStatus
    expires_at: datetime
    user_id: object | None = None

    def bind(self, user_id: object, now: datetime) -> None:
        if now >= self.expires_at:
            raise HandshakeExpired
        if self.status == HandshakeStatus.CONSUMED:
            raise HandshakeAlreadyUsed
        if self.status == HandshakeStatus.BOUND and self.user_id != user_id:
            raise HandshakeAlreadyUsed  # someone else already pressed Start on this nonce
        self.status = HandshakeStatus.BOUND
        self.user_id = user_id

    def can_exchange(self, verifier: str, now: datetime) -> bool:
        """False while still pending. Raises when the handshake can never succeed."""
        if not hmac.compare_digest(pkce_challenge(verifier), self.challenge):
            raise VerifierMismatch
        if self.status == HandshakeStatus.CONSUMED:
            raise HandshakeAlreadyUsed
        if now >= self.expires_at:
            raise HandshakeExpired
        return self.status == HandshakeStatus.BOUND

    def consume(self) -> None:
        self.status = HandshakeStatus.CONSUMED
