from decimal import Decimal
from functools import lru_cache
from typing import Literal

from pydantic import Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    env: Literal["local", "test", "staging", "production"] = "local"
    app_version: str = "0.1.0"
    public_app_url: str = "http://localhost:5173"
    log_json: bool = True
    sentry_dsn: str | None = None

    database_url: str = "postgresql+asyncpg://kainem:kainem@localhost:5432/kainem"
    redis_url: str = "redis://localhost:6379/0"

    # Telegram
    bot_token: SecretStr = SecretStr("")
    bot_username: str = "kainem_bot"
    bot_webhook_secret: SecretStr = SecretStr("")

    # Auth (ADR 0002: PWA login through the Telegram bot)
    jwt_secret: SecretStr = SecretStr("dev-only-change-me-dev-only-change-me")
    access_token_ttl_s: int = 15 * 60
    refresh_token_ttl_days: int = 30
    login_handshake_ttl_s: int = 10 * 60
    magic_link_ttl_s: int = 10 * 60
    # Browser path of the auth API (behind the /api reverse-proxy prefix): the refresh cookie is scoped to it.
    refresh_cookie_path: str = "/api/v1/auth"
    # Test-only endpoints (bind a handshake without Telegram). Never enabled in staging/production.
    enable_test_endpoints: bool = False

    # LLM (Sber500 accelerator proxy, OpenAI-compatible)
    llm_provider: Literal["openai_compatible", "fake"] = "fake"
    llm_base_url: str = "https://shared1.multitool.works:4000/v1"
    llm_api_key: SecretStr = SecretStr("")
    llm_timeout_s: float = 30.0
    llm_model_extraction: str = "deepseek-v4.1-flash"
    llm_model_chat: str = "gigachat-3-pro"

    # Spend control (RUB)
    llm_program_budget_rub: int = 50_000
    llm_budget_alert_thresholds: list[float] = Field(default_factory=lambda: [0.5, 0.8])
    llm_family_daily_quota_rub: Decimal = Decimal("50")

    # Analytics
    reporting_tz: str = "Europe/Moscow"
    analytics_preauth_rate_per_min: int = 60

    @property
    def secure_cookies(self) -> bool:
        return self.env in ("staging", "production")

    @property
    def test_endpoints_enabled(self) -> bool:
        return self.enable_test_endpoints and self.env in ("local", "test")

    @property
    def sync_database_url(self) -> str:
        """psycopg DSN for Procrastinate (it doesn't use asyncpg)."""
        return self.database_url.replace("postgresql+asyncpg://", "postgresql://")

    @property
    def llm_models_in_use(self) -> set[str]:
        return {self.llm_model_extraction, self.llm_model_chat}


@lru_cache
def get_settings() -> Settings:
    return Settings()
