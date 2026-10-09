"""Test-only endpoints (local/test env + ENABLE_TEST_ENDPOINTS). Simulate the bot side for e2e tests."""

import uuid
from datetime import UTC, datetime

from fastapi import APIRouter, HTTPException
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


class CaptureIn(BaseModel):
    tg_user_id: int = Field(ge=1)
    text: str = Field(min_length=1, max_length=4000)
    forwarded: bool = True


class DraftOut(BaseModel):
    id: uuid.UUID
    summary: str
    raw: bool


class CaptureOut(BaseModel):
    failure: str | None
    drafts: list[DraftOut]


class ConfirmIn(BaseModel):
    tg_user_id: int = Field(ge=1)


class ConfirmOut(BaseModel):
    status: str


async def _resolve(c: ContainerDep, tg_user_id: int) -> tuple[uuid.UUID, uuid.UUID]:
    user_id, family_id = await c.identity.resolve_telegram(tg_user_id)
    if user_id is None or family_id is None:
        raise HTTPException(404, "unknown telegram user")
    return user_id, family_id


@router.post("/capture", response_model=CaptureOut)
async def capture(body: CaptureIn, c: ContainerDep) -> CaptureOut:
    """What the bot does with a forwarded/written message: extract → draft cards."""
    user_id, family_id = await _resolve(c, body.tg_user_id)
    outcome = await c.capture.capture(
        user_id=user_id,
        family_id=family_id,
        text=body.text,
        source="forwarded" if body.forwarded else "own",
        written_at=datetime.now(UTC),
    )
    return CaptureOut(
        failure=outcome.failure, drafts=[DraftOut(id=d.id, summary=d.summary, raw=d.raw) for d in outcome.drafts]
    )


@router.post("/drafts/{draft_id}/confirm", response_model=ConfirmOut)
async def confirm_draft(draft_id: uuid.UUID, body: ConfirmIn, c: ContainerDep) -> ConfirmOut:
    """The «Сохранить» button on a draft card."""
    user_id, _ = await _resolve(c, body.tg_user_id)
    return ConfirmOut(status=(await c.capture.confirm(draft_id, user_id)).status)
