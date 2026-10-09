"""PWA login through the Telegram bot (ADR 0002)."""

import uuid
from typing import Annotated, Literal

from fastapi import APIRouter, Cookie, HTTPException, Response, status
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from planner.domain.families import login_deep_link
from planner.entrypoints.api.deps import ClientIpDep, ContainerDep, PlatformDep
from planner.modules.identity.service import AuthError, AuthTokens

router = APIRouter(prefix="/v1/auth", tags=["auth"])

REFRESH_COOKIE = "kn_refresh"
POLL_INTERVAL_MS = 2000
# Reasons after which the client must restart login; "pending" is not an error.
GONE_REASONS = {"expired", "used", "reused"}


class HandshakeStart(BaseModel):
    challenge: str = Field(min_length=43, max_length=43, pattern=r"^[A-Za-z0-9_-]+$")  # S256, base64url
    anonymous_id: uuid.UUID | None = None
    utm: dict[str, str] = Field(default_factory=dict, max_length=10)


class HandshakeStarted(BaseModel):
    nonce: str
    deep_link: str
    expires_at: str
    poll_interval_ms: int


class HandshakeExchange(BaseModel):
    verifier: str = Field(min_length=43, max_length=128)


class Pending(BaseModel):
    status: Literal["pending"] = "pending"


class MagicRedeem(BaseModel):
    token: str = Field(min_length=16, max_length=128)
    anonymous_id: uuid.UUID | None = None


class Session(BaseModel):
    access_token: str
    token_type: Literal["bearer"] = "bearer"
    expires_in: int
    user_id: uuid.UUID


class AuthFailure(BaseModel):
    reason: str


def _session_response(c: ContainerDep, tokens: AuthTokens, response: Response) -> Session:
    s = c.settings
    response.set_cookie(
        REFRESH_COOKIE,
        tokens.refresh_token,
        expires=tokens.refresh_expires_at,
        path=s.refresh_cookie_path,
        httponly=True,
        secure=s.secure_cookies,
        samesite="lax",
    )
    return Session(access_token=tokens.access_token, expires_in=tokens.expires_in, user_id=tokens.user_id)


def _failure(exc: AuthError) -> HTTPException:
    code = {"verifier_mismatch": 403, "invalid": 404}.get(exc.reason, 410 if exc.reason in GONE_REASONS else 401)
    return HTTPException(code, detail={"reason": exc.reason})


@router.post("/tg-handshake", status_code=status.HTTP_201_CREATED, response_model=HandshakeStarted)
async def start_handshake(body: HandshakeStart, c: ContainerDep, platform: PlatformDep, ip: ClientIpDep):
    """Step 1: the PWA gets a nonce and opens `t.me/<bot>?start=login_<nonce>`."""
    if not await c.rate_limiter.hit(f"hs-start:{ip}", c.settings.login_start_rate_per_min):
        raise HTTPException(429, "too many login attempts")
    started = await c.identity.start_handshake(
        challenge=body.challenge, platform=platform, anonymous_id=body.anonymous_id, utm=body.utm
    )
    return HandshakeStarted(
        nonce=started.nonce,
        deep_link=login_deep_link(c.settings.bot_username, started.nonce),
        expires_at=started.expires_at.isoformat(),
        poll_interval_ms=POLL_INTERVAL_MS,
    )


@router.post(
    "/tg-handshake/{nonce}/exchange",
    response_model=Session,
    responses={202: {"model": Pending}, 403: {"model": AuthFailure}, 410: {"model": AuthFailure}},
)
async def exchange_handshake(nonce: str, body: HandshakeExchange, c: ContainerDep, response: Response, ip: ClientIpDep):
    """Step 2 (polled): 202 until the user presses Start in the bot, then a session, exactly once."""
    if not await c.rate_limiter.hit(f"hs-exchange:{ip}", c.settings.login_poll_rate_per_min):
        raise HTTPException(429, "polling too fast")
    try:
        tokens = await c.identity.exchange_handshake(nonce, body.verifier)
    except AuthError as exc:
        raise _failure(exc) from None
    if tokens is None:
        return JSONResponse(Pending().model_dump(), status_code=202)
    return _session_response(c, tokens, response)


@router.post("/magic", response_model=Session, responses={410: {"model": AuthFailure}})
async def redeem_magic_link(
    body: MagicRedeem, c: ContainerDep, platform: PlatformDep, response: Response, ip: ClientIpDep
):
    """The single-use link from the bot message ("Вот пространство семьи — <link>")."""
    if not await c.rate_limiter.hit(f"magic:{ip}", c.settings.magic_link_rate_per_min):
        raise HTTPException(429, "too many attempts")
    try:
        tokens = await c.identity.redeem_magic_token(body.token, platform=platform, anonymous_id=body.anonymous_id)
    except AuthError as exc:
        raise HTTPException(410 if exc.reason in GONE_REASONS else 404, detail={"reason": exc.reason}) from None
    return _session_response(c, tokens, response)


@router.post("/refresh", response_model=Session, responses={401: {"model": AuthFailure}})
async def refresh(c: ContainerDep, response: Response, kn_refresh: Annotated[str | None, Cookie()] = None):
    """Rotates the refresh cookie. Reusing an old one revokes the whole login (theft detection)."""
    if not kn_refresh:
        raise HTTPException(401, detail={"reason": "no_session"})
    try:
        tokens = await c.identity.refresh(kn_refresh)
    except AuthError as exc:
        response.delete_cookie(REFRESH_COOKIE, path=c.settings.refresh_cookie_path)
        raise HTTPException(401, detail={"reason": exc.reason}) from None
    return _session_response(c, tokens, response)


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
async def logout(c: ContainerDep, kn_refresh: Annotated[str | None, Cookie()] = None) -> Response:
    if kn_refresh:
        await c.identity.logout(kn_refresh)
    response = Response(status_code=204)
    response.delete_cookie(REFRESH_COOKIE, path=c.settings.refresh_cookie_path)
    return response
