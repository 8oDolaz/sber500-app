from fastapi import APIRouter, HTTPException, Request

from planner.entrypoints.api.deps import ContainerDep, DisplayModeDep, PlatformDep, PrincipalDep
from planner.modules.analytics.ingest import IngestBatch, IngestResult, RateLimited

router = APIRouter(prefix="/v1/analytics", tags=["analytics"])


@router.post("/events", response_model=IngestResult)
async def ingest_events(
    batch: IngestBatch,
    request: Request,
    c: ContainerDep,
    principal: PrincipalDep,
    platform: PlatformDep,
    display_mode: DisplayModeDep,
) -> IngestResult:
    """Batched client events. Without a session only pre-login funnel events are accepted."""
    client_ip = request.client.host if request.client else "unknown"
    try:
        return await c.ingest.ingest(
            batch, platform=platform, display_mode=display_mode, principal=principal, client_ip=client_ip
        )
    except RateLimited:
        raise HTTPException(429, "too many analytics events") from None
