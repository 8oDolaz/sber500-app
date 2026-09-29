import time
import uuid
from contextlib import asynccontextmanager

import structlog
from fastapi import FastAPI, Request, Response

from planner.bootstrap import Container, build_container
from planner.entrypoints.api.deps import parse_platform
from planner.entrypoints.api.routers import analytics, auth, health, me, planning, telegram, testing
from planner.entrypoints.bot.app import build_bot, build_dispatcher
from planner.infra.telemetry import HTTP_LATENCY, HTTP_REQUESTS, configure_logging, configure_sentry
from planner.modules.analytics.activity import EXCLUDED_API_PATHS
from planner.settings import Settings, get_settings

log = structlog.get_logger(__name__)


def create_app(settings: Settings | None = None, container: Container | None = None) -> FastAPI:
    settings = settings or get_settings()

    if settings.env in ("staging", "production") and "dev-only" in settings.jwt_secret.get_secret_value():
        raise RuntimeError("JWT_SECRET must be set outside local/test")

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        configure_logging(json=settings.log_json)
        configure_sentry(settings.sentry_dsn, env=settings.env, release=settings.app_version)
        c = container or build_container(settings)
        app.state.container = c
        app.state.bot = build_bot(settings)
        app.state.dispatcher = build_dispatcher(c)
        try:
            yield
        finally:
            if app.state.bot is not None:
                await app.state.bot.session.close()
            if container is None:
                await c.aclose()

    app = FastAPI(title="kainem API", version=settings.app_version, lifespan=lifespan)

    @app.middleware("http")
    async def observe(request: Request, call_next) -> Response:
        request_id = request.headers.get("x-request-id") or uuid.uuid4().hex
        structlog.contextvars.bind_contextvars(request_id=request_id)
        started = time.perf_counter()
        status = 500
        try:
            response = await call_next(request)
            status = response.status_code
            response.headers["x-request-id"] = request_id
            return response
        finally:
            route = request.scope.get("route")
            path = getattr(route, "path", "unmatched")
            HTTP_REQUESTS.labels(request.method, path, str(status)).inc()
            HTTP_LATENCY.labels(request.method, path).observe(time.perf_counter() - started)
            principal = getattr(request.state, "principal", None)
            if principal is not None and status < 500 and path not in EXCLUDED_API_PATHS:
                c: Container = request.app.state.container
                platform = parse_platform(request.headers.get("x-client-platform"))
                if platform is not None:
                    await c.activity.record(principal.user_id, platform, principal.family_id)
            structlog.contextvars.unbind_contextvars("request_id")

    app.include_router(health.router)
    app.include_router(analytics.router)
    app.include_router(telegram.router)
    app.include_router(auth.router)
    app.include_router(me.router)
    app.include_router(planning.router)
    if settings.test_endpoints_enabled:
        app.include_router(testing.router)
    return app
