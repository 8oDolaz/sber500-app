from datetime import UTC, datetime, timedelta

import pytest

from planner.domain.identity import (
    HandshakeAlreadyUsed,
    HandshakeExpired,
    HandshakeStatus,
    LoginHandshake,
    VerifierMismatch,
    hash_token,
    new_token,
    pkce_challenge,
)

NOW = datetime(2026, 9, 29, 12, 0, tzinfo=UTC)
VERIFIER = "v" * 43


def handshake() -> LoginHandshake:
    return LoginHandshake(
        nonce="n",
        challenge=pkce_challenge(VERIFIER),
        status=HandshakeStatus.PENDING,
        expires_at=NOW + timedelta(minutes=10),
    )


def test_pkce_matches_rfc7636_example() -> None:
    # RFC 7636 appendix B
    assert (
        pkce_challenge("dBjftJeZ4CVP-mB92K27uhbUJU1p1r_wW1gFWFOEjXk") == "E9Melhoa2OwvFrEMTJguCHaoeK1t8URWbuGJSstw-cM"
    )


def test_tokens_are_random_and_hash_is_stable() -> None:
    assert new_token() != new_token()
    assert len(new_token()) == 32
    assert hash_token("abc") == hash_token("abc") != hash_token("abd")


def test_pending_cannot_be_exchanged_yet() -> None:
    assert handshake().can_exchange(VERIFIER, NOW) is False


def test_bind_then_exchange_then_consume() -> None:
    hs = handshake()
    hs.bind("user-1", NOW)
    assert hs.can_exchange(VERIFIER, NOW) is True
    hs.consume()
    with pytest.raises(HandshakeAlreadyUsed):
        hs.can_exchange(VERIFIER, NOW)


def test_wrong_verifier_is_rejected_even_when_bound() -> None:
    hs = handshake()
    hs.bind("user-1", NOW)
    with pytest.raises(VerifierMismatch):
        hs.can_exchange("x" * 43, NOW)


def test_expired_handshake_cannot_be_bound_or_exchanged() -> None:
    later = NOW + timedelta(minutes=11)
    with pytest.raises(HandshakeExpired):
        handshake().bind("user-1", later)
    hs = handshake()
    hs.bind("user-1", NOW)
    with pytest.raises(HandshakeExpired):
        hs.can_exchange(VERIFIER, later)


def test_rebinding_by_same_user_is_idempotent_but_other_user_is_rejected() -> None:
    hs = handshake()
    hs.bind("user-1", NOW)
    hs.bind("user-1", NOW)
    with pytest.raises(HandshakeAlreadyUsed):
        hs.bind("user-2", NOW)
