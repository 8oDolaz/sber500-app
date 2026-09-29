"""Family commands and queries (ARCHITECTURE §5.2)."""

import uuid
from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from planner.domain.families import Role, family_name_for
from planner.domain.identity import new_token
from planner.infra.db import Database
from planner.infra.ids import new_id
from planner.modules.analytics.catalog import FamilyCreated, InviteCreated, Platform
from planner.modules.analytics.tracker import EventContext, Tracker
from planner.modules.families.tables import FamilyRow, InviteRow, MemberRow
from planner.modules.identity.tables import UserRow


@dataclass(frozen=True, slots=True)
class FamilySummary:
    id: uuid.UUID
    name: str
    role: Role


@dataclass(frozen=True, slots=True)
class LeaderFamily:
    family: FamilyRow
    invite: InviteRow
    created: bool


class FamilyService:
    def __init__(self, db: Database, tracker: Tracker, app_version: str) -> None:
        self._db = db
        self._tracker = tracker
        self._app_version = app_version

    async def ensure_leader_family(self, session: AsyncSession, user: UserRow, platform: Platform) -> LeaderFamily:
        """Registers the user's family space on first contact. Idempotent: the caller holds the user row lock.

        A user who already belongs to any family (e.g. joined as acceptor) keeps it; no second family is created.
        """
        ctx = EventContext(platform=platform, user_id=user.id, app_version=self._app_version)
        existing = await session.scalar(
            select(MemberRow).where(MemberRow.user_id == user.id).order_by(MemberRow.created_at).limit(1)
        )
        if existing is not None:
            family = await session.get(FamilyRow, existing.family_id)
            assert family is not None
            if user.active_family_id is None:
                user.active_family_id = family.id
            invite = await self._active_invite(session, family.id) or self._new_invite(session, family.id, user.id, ctx)
            return LeaderFamily(family, invite, created=False)

        family = FamilyRow(id=new_id(), name=family_name_for(user.first_name), created_by=user.id)
        session.add(family)
        await session.flush()
        session.add(
            MemberRow(id=new_id(), family_id=family.id, user_id=user.id, display_name=user.first_name, role=Role.OWNER)
        )
        user.active_family_id = family.id
        ctx = EventContext(platform=platform, user_id=user.id, family_id=family.id, app_version=self._app_version)
        self._tracker.track(session, FamilyCreated(family_id=family.id), ctx)
        invite = self._new_invite(session, family.id, user.id, ctx)
        return LeaderFamily(family, invite, created=True)

    async def my_families(self, user_id: uuid.UUID) -> list[FamilySummary]:
        async with self._db.sessions() as session:
            rows = (
                await session.execute(
                    select(FamilyRow.id, FamilyRow.name, MemberRow.role)
                    .join(MemberRow, MemberRow.family_id == FamilyRow.id)
                    .where(MemberRow.user_id == user_id)
                    .order_by(MemberRow.created_at)
                )
            ).all()
        return [FamilySummary(id=r.id, name=r.name, role=Role(r.role)) for r in rows]

    async def _active_invite(self, session: AsyncSession, family_id: uuid.UUID) -> InviteRow | None:
        return await session.scalar(
            select(InviteRow)
            .where(InviteRow.family_id == family_id, InviteRow.revoked_at.is_(None), InviteRow.expires_at.is_(None))
            .order_by(InviteRow.created_at.desc())
            .limit(1)
        )

    def _new_invite(
        self, session: AsyncSession, family_id: uuid.UUID, created_by: uuid.UUID, ctx: EventContext
    ) -> InviteRow:
        invite = InviteRow(id=new_id(), family_id=family_id, token=new_token(), created_by=created_by)
        session.add(invite)
        self._tracker.track(session, InviteCreated(invite_id=invite.id), ctx)
        return invite
