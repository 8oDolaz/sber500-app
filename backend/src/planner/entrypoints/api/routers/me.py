import uuid

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from planner.domain.families import Role
from planner.entrypoints.api.deps import AuthDep, ContainerDep
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


@router.get("/me", response_model=Me)
async def get_me(principal: AuthDep, c: ContainerDep) -> Me:
    async with c.db.sessions() as session:
        user = await session.get(UserRow, principal.user_id)
    if user is None:
        raise HTTPException(401, "user no longer exists")
    families = await c.families.my_families(user.id)
    return Me(
        user=UserOut(id=user.id, first_name=user.first_name),
        onboarding_completed=user.onboarding_completed_at is not None,
        active_family_id=user.active_family_id,
        families=[FamilyOut(id=f.id, name=f.name, role=f.role) for f in families],
    )
