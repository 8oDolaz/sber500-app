"""Prometheus metrics and logging/Sentry setup (ARCHITECTURE §9.1 technical metrics)."""

import logging
import sys

import structlog
from prometheus_client import Counter, Gauge, Histogram

# --- API ---
HTTP_REQUESTS = Counter("http_requests_total", "API requests", ["method", "route", "status"])
HTTP_LATENCY = Histogram("http_request_duration_seconds", "API latency", ["method", "route"])

# --- Bot ---
BOT_UPDATES = Counter("bot_updates_total", "Telegram updates processed", ["update_type", "status"])

# --- LLM ---
LLM_CALLS = Counter("llm_calls_total", "LLM provider calls", ["provider", "model", "feature", "status"])
LLM_LATENCY = Histogram(
    "llm_call_duration_seconds",
    "LLM call latency",
    ["provider", "model"],
    buckets=(0.25, 0.5, 1, 2, 4, 8, 15, 30, 60),
)
LLM_SPEND_RUB = Gauge("llm_spend_rub_total", "Total LLM spend recorded in the ledger, RUB")
LLM_LEDGER_WRITE_FAILED = Counter("llm_ledger_write_failed_total", "Failed llm_usage ledger writes")

# --- Outbox / jobs ---
OUTBOX_DISPATCHED = Counter("outbox_dispatched_total", "Outbox messages processed", ["topic", "status"])
OUTBOX_LAG = Gauge("outbox_lag_seconds", "Age of the oldest pending outbox message")

# --- Analytics ---
ANALYTICS_INGESTED = Counter("analytics_events_ingested_total", "Accepted analytics events", ["source"])
ANALYTICS_REJECTED = Counter("analytics_events_rejected_total", "Rejected analytics events", ["reason"])


def configure_logging(*, json: bool, level: int = logging.INFO) -> None:
    processors: list[structlog.types.Processor] = [
        structlog.contextvars.merge_contextvars,
        structlog.processors.add_log_level,
        structlog.processors.TimeStamper(fmt="iso", utc=True),
        structlog.processors.StackInfoRenderer(),
        structlog.processors.format_exc_info,
    ]
    renderer = structlog.processors.JSONRenderer() if json else structlog.dev.ConsoleRenderer()
    structlog.configure(
        processors=[*processors, renderer],
        wrapper_class=structlog.make_filtering_bound_logger(level),
        logger_factory=structlog.PrintLoggerFactory(sys.stdout),
        cache_logger_on_first_use=True,
    )
    logging.basicConfig(level=level, stream=sys.stdout, format="%(message)s")


def configure_sentry(dsn: str | None, *, env: str, release: str) -> None:
    if not dsn:
        return
    import sentry_sdk

    sentry_sdk.init(dsn=dsn, environment=env, release=release, traces_sample_rate=0.0)
