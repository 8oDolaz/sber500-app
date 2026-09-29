"""Test-only endpoints (local/test env + ENABLE_TEST_ENDPOINTS). Simulate the bot side for e2e tests."""

from fastapi import APIRouter
from pydantic import BaseModel, Field

from planner.entrypoints.api.deps import ContainerDep
from planner.modules.identity.service import TelegramProfile

router = APIRouter(prefix="/v1/test", tags=["test"], include_in_schema=False)


class BotStart(BaseModel):
    tg_user_id: int = Field(ge=1)
    first_name: str = "Тест"
    payload: str | None = None  # what follows /start: login_<nonce>, inv_<token> or nothing


class BindRequest(BaseModel):
    tg_user_id: int = Field(ge=1)
    first_name: str = "Тест"


class StartOut(BaseModel):
    kind: str
    handshake_error: str | None
    magic_token: str | None
    invite_link: str | None
    family_name: str | None


async def _start(c: ContainerDep, tg_user_id: int, first_name: str, payload: str | None) -> StartOut:
    result = await c.registration.handle_start(
        TelegramProfile(tg_user_id=tg_user_id, first_name=first_name), payload, is_test=True
    )
    return StartOut(
        kind=result.kind,
        handshake_error=result.handshake_error,
        magic_token=result.magic_token,
        invite_link=result.invite_link,
        family_name=result.family_name,
    )


@router.post("/bot-start", response_model=StartOut)
async def bot_start(body: BotStart, c: ContainerDep) -> StartOut:
    """Does what `/start <payload>` does in the bot, for a test user (is_test=true)."""
    return await _start(c, body.tg_user_id, body.first_name, body.payload)


@router.post("/tg-handshake/{nonce}/bind", response_model=StartOut)
async def bind_handshake(nonce: str, body: BindRequest, c: ContainerDep) -> StartOut:
    return await _start(c, body.tg_user_id, body.first_name, f"login_{nonce}")
