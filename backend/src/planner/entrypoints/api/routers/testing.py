"""Test-only endpoints (local/test env + ENABLE_TEST_ENDPOINTS). Simulate the bot side of login for e2e."""

from fastapi import APIRouter
from pydantic import BaseModel, Field

from planner.entrypoints.api.deps import ContainerDep
from planner.modules.identity.service import TelegramProfile

router = APIRouter(prefix="/v1/test", tags=["test"], include_in_schema=False)


class BindRequest(BaseModel):
    tg_user_id: int = Field(ge=1)
    first_name: str = "Тест"


class BindResult(BaseModel):
    kind: str
    handshake_error: str | None
    magic_token: str | None
    invite_link: str | None


@router.post("/tg-handshake/{nonce}/bind", response_model=BindResult)
async def bind_handshake(nonce: str, body: BindRequest, c: ContainerDep) -> BindResult:
    """Does what `/start login_<nonce>` does in the bot, for a test user (is_test=true)."""
    result = await c.registration.handle_start(
        TelegramProfile(tg_user_id=body.tg_user_id, first_name=body.first_name), f"login_{nonce}", is_test=True
    )
    return BindResult(
        kind=result.kind,
        handshake_error=result.handshake_error,
        magic_token=result.magic_token,
        invite_link=result.invite_link,
    )
