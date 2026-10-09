import uuid
from typing import Literal

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from planner.domain.families import Role
from planner.entrypoints.api.deps import AuthDep, ContainerDep, PlatformDep
from planner.modules.identity.tables import UserRow

router = APIRouter(prefix="/v1", tags=["me"])


class FamilyOut(BaseModel):
    id: uuid.UUID
    name: str
    role: Role


class UserOut(BaseModel):
    id: uuid.UUID
    first_name: str


class Me(BaseModel):
    user: UserOut
    onboarding_completed: bool
    active_family_id: uuid.UUID | None
    families: list[FamilyOut]
    bot_link: str  # "open the bot" buttons (help screen, empty states)


class MeUpdate(BaseModel):
    # Only "done" is meaningful: onboarding can't be un-completed.
    onboarding_completed: Literal[True]


async def _me(c: ContainerDep, user_id: uuid.UUID) -> Me:
    async with c.db.sessions() as session:
        user = await session.get(UserRow, user_id)
    if user is None:
        raise HTTPException(401, "user no longer exists")
    families = await c.families.my_families(user.id)
    return Me(
        user=UserOut(id=user.id, first_name=user.first_name),
        onboarding_completed=user.onboarding_completed_at is not None,
        active_family_id=user.active_family_id,
        families=[FamilyOut(id=f.id, name=f.name, role=f.role) for f in families],
        bot_link=f"https://t.me/{c.settings.bot_username}",
    )


@router.get("/me", response_model=Me)
async def get_me(principal: AuthDep, c: ContainerDep) -> Me:
    return await _me(c, principal.user_id)


@router.patch("/me", response_model=Me)
async def update_me(body: MeUpdate, principal: AuthDep, c: ContainerDep, platform: PlatformDep) -> Me:
    if body.onboarding_completed:
        await c.registration.complete_onboarding(principal.user_id, platform, c.settings.app_version)
    return await _me(c, principal.user_id)


class ActiveFamily(BaseModel):
    family_id: uuid.UUID


@router.put("/me/active-family", response_model=Me, responses={403: {"description": "not a member"}})
async def set_active_family(body: ActiveFamily, principal: AuthDep, c: ContainerDep) -> Me:
    """Switch the family shown in the app (a user can belong to several families)."""
    if not await c.registration.switch_family(principal.user_id, body.family_id):
        raise HTTPException(403, "not a member of this family")
    return await _me(c, principal.user_id)
