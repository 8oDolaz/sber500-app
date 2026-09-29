"""Family commands and queries (ARCHITECTURE §5.2)."""

import uuid
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Literal

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


InviteStatus = Literal["valid", "expired", "invalid"]


@dataclass(frozen=True, slots=True)
class FamilyInvite:
    family: FamilyRow
    invite: InviteRow


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
        # Prefer the active family; fall back to the oldest membership.
        existing = await session.scalar(
            select(MemberRow)
            .where(MemberRow.user_id == user.id)
            .order_by((MemberRow.family_id == user.active_family_id).desc(), MemberRow.created_at)
            .limit(1)
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

    async def find_invite(self, session: AsyncSession, token: str) -> tuple[InviteRow | None, InviteStatus]:
        invite = await session.scalar(select(InviteRow).where(InviteRow.token == token).with_for_update())
        if invite is None:
            return None, "invalid"
        now = datetime.now(UTC)
        if invite.revoked_at is not None or (invite.expires_at is not None and invite.expires_at <= now):
            return invite, "expired"
        return invite, "valid"

    async def accept_invite(
        self, session: AsyncSession, user: UserRow, invite: InviteRow
    ) -> Literal["accepted", "already_member"]:
        """The acceptor joins as an adult and the family becomes active. The caller holds the user row lock.

        The caller emits `invite_opened` / `invite_accepted` (in that order, for the funnel)."""
        user.active_family_id = invite.family_id  # they came for this family: show it
        member = await session.scalar(
            select(MemberRow).where(MemberRow.family_id == invite.family_id, MemberRow.user_id == user.id)
        )
        if member is not None:
            return "already_member"
        session.add(
            MemberRow(
                id=new_id(),
                family_id=invite.family_id,
                user_id=user.id,
                display_name=user.first_name,
                role=Role.ADULT,
            )
        )
        invite.uses += 1
        return "accepted"

    async def get_family(self, session: AsyncSession, family_id: uuid.UUID) -> FamilyRow:
        family = await session.get(FamilyRow, family_id)
        assert family is not None
        return family

    async def active_family_invite(
        self, session: AsyncSession, user: UserRow, platform: Platform
    ) -> FamilyInvite | None:
        """The invite of the user's active family (created when missing) — for re-sharing it."""
        if user.active_family_id is None:
            return None
        family = await session.get(FamilyRow, user.active_family_id)
        if family is None:
            return None
        invite = await self._active_invite(session, family.id)
        if invite is None:
            ctx = EventContext(platform, user.id, family.id, app_version=self._app_version)
            invite = self._new_invite(session, family.id, user.id, ctx)
        return FamilyInvite(family, invite)

    async def set_active_family(self, session: AsyncSession, user: UserRow, family_id: uuid.UUID) -> bool:
        """False when the user is not a member of that family."""
        is_member = await session.scalar(
            select(MemberRow.id).where(MemberRow.family_id == family_id, MemberRow.user_id == user.id)
        )
        if is_member is None:
            return False
        user.active_family_id = family_id
        return True

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
