"""Composition root: wires ports to adapters. The only module allowed to import everything."""

from dataclasses import dataclass
from datetime import timedelta

from redis.asyncio import Redis

from planner.infra.db import Database
from planner.infra.outbox import OutboxDispatcher
from planner.infra.ratelimit import RateLimiter
from planner.infra.redis import create_redis
from planner.modules.analytics.activity import ActivityRecorder
from planner.modules.analytics.catalog import LlmBudgetExceeded, Platform
from planner.modules.analytics.ingest import IngestService
from planner.modules.analytics.llm_ledger import FamilyQuota, LlmLedger, PriceBook, SpendMonitor
from planner.modules.analytics.tracker import (
    OUTBOX_TOPIC,
    AnalyticsSink,
    EventContext,
    PostgresSink,
    Tracker,
    outbox_handler,
)
from planner.modules.assistant.llm_gateway.fake import FakeProvider
from planner.modules.assistant.llm_gateway.gateway import LLMGateway
from planner.modules.assistant.llm_gateway.models_health import ModelsHealth
from planner.modules.assistant.llm_gateway.openai_compatible import OpenAICompatibleProvider
from planner.modules.assistant.llm_gateway.port import LLMProvider
from planner.modules.families.service import FamilyService
from planner.modules.identity.service import AuthConfig, IdentityService
from planner.modules.notifications.bot_chats import BotChatService
from planner.modules.registration.service import RegistrationService
from planner.settings import Settings


@dataclass
class Container:
    settings: Settings
    db: Database
    redis: Redis
    tracker: Tracker
    dispatcher: OutboxDispatcher
    ingest: IngestService
    activity: ActivityRecorder
    ledger: LlmLedger
    llm: LLMGateway
    models_health: ModelsHealth
    spend_monitor: SpendMonitor
    identity: IdentityService
    families: FamilyService
    registration: RegistrationService
    bot_chats: BotChatService
    rate_limiter: RateLimiter

    async def aclose(self) -> None:
        await self.redis.aclose()
        await self.db.dispose()


def build_llm_provider(settings: Settings) -> LLMProvider:
    if settings.llm_provider == "openai_compatible":
        return OpenAICompatibleProvider(
            base_url=settings.llm_base_url,
            api_key=settings.llm_api_key.get_secret_value(),
            timeout_s=settings.llm_timeout_s,
        )
    return FakeProvider(models=sorted(settings.llm_models_in_use))


def build_container(settings: Settings, *, llm_provider: LLMProvider | None = None) -> Container:
    db = Database(settings.database_url)
    redis = create_redis(settings.redis_url)
    tracker = Tracker()
    sinks: list[AnalyticsSink] = [PostgresSink()]

    dispatcher = OutboxDispatcher(db)
    dispatcher.register(OUTBOX_TOPIC, outbox_handler(sinks))

    quota = FamilyQuota(redis, settings.llm_family_daily_quota_rub, settings.reporting_tz)
    ledger = LlmLedger(db, PriceBook(db), quota)

    async def on_budget_exceeded(model: str, feature: str) -> None:
        async with db.transaction() as session:
            tracker.track(
                session,
                LlmBudgetExceeded(scope="program", model=model, feature=feature),
                EventContext(platform=Platform.SERVER, app_version=settings.app_version),
            )

    llm = LLMGateway(
        llm_provider or build_llm_provider(settings), ledger, quota=quota, on_budget_exceeded=on_budget_exceeded
    )
    identity = IdentityService(
        db,
        tracker,
        AuthConfig(
            jwt_secret=settings.jwt_secret.get_secret_value(),
            access_ttl=timedelta(seconds=settings.access_token_ttl_s),
            refresh_ttl=timedelta(days=settings.refresh_token_ttl_days),
            handshake_ttl=timedelta(seconds=settings.login_handshake_ttl_s),
            magic_ttl=timedelta(seconds=settings.magic_link_ttl_s),
            app_version=settings.app_version,
        ),
    )
    families = FamilyService(db, tracker, settings.app_version)
    registration = RegistrationService(
        db, identity, families, bot_username=settings.bot_username, public_app_url=settings.public_app_url
    )
    return Container(
        settings=settings,
        db=db,
        redis=redis,
        tracker=tracker,
        dispatcher=dispatcher,
        ingest=IngestService(db, redis, sinks, settings.analytics_preauth_rate_per_min),
        activity=ActivityRecorder(db, redis, settings.reporting_tz),
        ledger=ledger,
        llm=llm,
        models_health=ModelsHealth(llm, settings.llm_models_in_use),
        spend_monitor=SpendMonitor(db, redis, settings.llm_program_budget_rub, settings.llm_budget_alert_thresholds),
        identity=identity,
        families=families,
        registration=registration,
        bot_chats=BotChatService(db, tracker, identity, settings.app_version),
        rate_limiter=RateLimiter(redis),
    )
