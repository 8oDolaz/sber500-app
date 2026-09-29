"""Analytics event catalog (ARCHITECTURE §9.3, §9.8).

Adding a metric = define a Pydantic model here with `@analytics_event(...)` and call
`tracker.track(...)` (server) or `track()` in the frontend (client).
"""

from dataclasses import dataclass
from enum import StrEnum
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict


class Platform(StrEnum):
    PWA = "pwa"
    TELEGRAM_BOT = "telegram_bot"
    TELEGRAM_MINI_APP = "telegram_mini_app"
    SERVER = "server"


class DisplayMode(StrEnum):
    BROWSER = "browser"
    STANDALONE = "standalone"


@dataclass(frozen=True)
class EventSpec:
    name: str
    version: int
    model: type[BaseModel]
    source: Literal["server", "client"]
    counts_as_active: bool
    preauth_allowed: bool  # client events accepted without a session (pre-login funnel)
    owner: str


CATALOG: dict[str, EventSpec] = {}


class EventProps(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


def analytics_event(
    name: str,
    *,
    version: int = 1,
    source: Literal["server", "client"] = "server",
    counts_as_active: bool = False,
    preauth_allowed: bool = False,
    owner: str = "product",
):
    def register[T: type[BaseModel]](model: T) -> T:
        if name in CATALOG:
            raise ValueError(f"analytics event {name!r} registered twice")
        if preauth_allowed and source != "client":
            raise ValueError("only client events can be accepted pre-auth")
        CATALOG[name] = EventSpec(name, version, model, source, counts_as_active, preauth_allowed, owner)
        model.__analytics_name__ = name  # type: ignore[attr-defined]
        return model

    return register


def spec_for(model: BaseModel) -> EventSpec:
    name = getattr(type(model), "__analytics_name__", None)
    if name is None:
        raise TypeError(f"{type(model).__name__} is not a registered analytics event")
    return CATALOG[name]


# ---------------------------------------------------------------- client events
Screen = Literal["splash", "welcome", "onboarding", "home", "help"]


@analytics_event("screen_viewed", source="client", preauth_allowed=True)
class ScreenViewed(EventProps):
    screen: Screen


@analytics_event("register_clicked", source="client", preauth_allowed=True)
class RegisterClicked(EventProps):
    pass


@analytics_event("a2hs_prompted", source="client", preauth_allowed=True)
class A2hsPrompted(EventProps):
    os: Literal["android", "ios", "desktop", "other"]


@analytics_event("a2hs_accepted", source="client", preauth_allowed=True)
class A2hsAccepted(EventProps):
    os: Literal["android", "ios", "desktop", "other"]


@analytics_event("a2hs_instructions_shown", source="client", preauth_allowed=True)
class A2hsInstructionsShown(EventProps):
    os: Literal["android", "ios", "desktop", "other"]


@analytics_event("how_to_clicked", source="client")
class HowToClicked(EventProps):
    pass


# ---------------------------------------------------------------- server events
@analytics_event("llm_budget_exceeded", owner="platform")
class LlmBudgetExceeded(EventProps):
    scope: Literal["program", "family"]
    model: str
    feature: str


# ---------------------------------------------------------------- identity & families (M1)
LoginMethod = Literal["poll", "test"]  # magic-link logins are tracked as magic_link_redeemed


@analytics_event("login_handshake_started", owner="identity")
class LoginHandshakeStarted(EventProps):
    handshake_id: UUID
    utm_source: str | None = None
    utm_medium: str | None = None
    utm_campaign: str | None = None


@analytics_event("login_handshake_completed", counts_as_active=True, owner="identity")
class LoginHandshakeCompleted(EventProps):
    handshake_id: UUID
    is_new_user: bool
    method: LoginMethod


@analytics_event("magic_link_redeemed", owner="identity")
class MagicLinkRedeemed(EventProps):
    pass


@analytics_event("magic_link_rejected", owner="identity")
class MagicLinkRejected(EventProps):
    reason: Literal["expired", "used", "invalid"]


@analytics_event("user_signed_up", owner="identity")
class UserSignedUp(EventProps):
    """Exactly once per user, in the transaction that creates the User row (ARCHITECTURE §9.4)."""

    platform: Literal["pwa", "telegram_bot"]  # where signup began
    acquisition_source: Literal["organic", "invite", "utm"]
    invite_id: UUID | None = None
    referrer_user_id: UUID | None = None
    utm_source: str | None = None
    utm_medium: str | None = None
    utm_campaign: str | None = None
    locale: str | None = None


@analytics_event("family_created", owner="families")
class FamilyCreated(EventProps):
    family_id: UUID


@analytics_event("invite_created", owner="families")
class InviteCreated(EventProps):
    invite_id: UUID


# ---------------------------------------------------------------- bot delivery
@analytics_event("bot_blocked", owner="notifications")
class BotBlocked(EventProps):
    pass


@analytics_event("bot_unblocked", owner="notifications")
class BotUnblocked(EventProps):
    pass


@analytics_event("bot_message_failed", owner="notifications")
class BotMessageFailed(EventProps):
    reason: Literal["forbidden", "rate_limited", "other"]
    template: str
