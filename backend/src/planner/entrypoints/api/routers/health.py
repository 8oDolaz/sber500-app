from fastapi import APIRouter, Response
from prometheus_client import CONTENT_TYPE_LATEST, generate_latest
from pydantic import BaseModel
from sqlalchemy import text

from planner.entrypoints.api.deps import ContainerDep

router = APIRouter(tags=["ops"])


class LlmModelsHealth(BaseModel):
    ok: bool
    provider: str
    missing: list[str]
    error: str | None = None


class Readiness(BaseModel):
    ok: bool
    database: bool
    redis: bool
    llm_models: LlmModelsHealth


@router.get("/healthz")
async def healthz() -> dict[str, str]:
    """Liveness: the process is up."""
    return {"status": "ok"}


@router.get("/readyz", response_model=Readiness)
async def readyz(c: ContainerDep, response: Response) -> Readiness:
    """Readiness: dependencies reachable and the configured LLM models still exist on the proxy."""
    try:
        async with c.db.sessions() as s:
            await s.execute(text("SELECT 1"))
        db_ok = True
    except Exception:  # noqa: BLE001
        db_ok = False
    try:
        redis_ok = bool(await c.redis.ping())
    except Exception:  # noqa: BLE001
        redis_ok = False
    models = await c.models_health.status()
    # A missing model degrades the assistant but not the whole app: report it, don't fail readiness.
    ok = db_ok and redis_ok
    if not ok:
        response.status_code = 503
    return Readiness(
        ok=ok,
        database=db_ok,
        redis=redis_ok,
        llm_models=LlmModelsHealth(
            ok=models.ok, provider=c.llm.provider_name, missing=models.missing, error=models.error
        ),
    )


@router.get("/metrics", include_in_schema=False)
async def metrics() -> Response:
    return Response(generate_latest(), media_type=CONTENT_TYPE_LATEST)
