"""Can we still message this person? Tracks bot blocks (an early churn signal, ARCHITECTURE §8)."""

from datetime import UTC, datetime
from typing import Literal

from sqlalchemy.dialects.postgresql import insert

from planner.infra.db import Database
from planner.modules.analytics.catalog import BotBlocked, BotMessageFailed, BotUnblocked, Platform
from planner.modules.analytics.tracker import EventContext, Tracker
from planner.modules.identity.service import IdentityService
from planner.modules.notifications.tables import BotChatRow


class BotChatService:
    def __init__(self, db: Database, tracker: Tracker, identity: IdentityService, app_version: str) -> None:
        self._db = db
        self._tracker = tracker
        self._identity = identity
        self._app_version = app_version

    async def set_blocked(self, tg_user_id: int, blocked: bool) -> None:
        user_id, family_id = await self._identity.resolve_telegram(tg_user_id)
        now = datetime.now(UTC)
        async with self._db.transaction() as session:
            await session.execute(
                insert(BotChatRow)
                .values(tg_user_id=tg_user_id, user_id=user_id, blocked_at=now if blocked else None, updated_at=now)
                .on_conflict_do_update(
                    index_elements=[BotChatRow.tg_user_id],
                    set_={"blocked_at": now if blocked else None, "updated_at": now, "user_id": user_id},
                )
            )
            ctx = EventContext(Platform.TELEGRAM_BOT, user_id, family_id, app_version=self._app_version)
            self._tracker.track(session, BotBlocked() if blocked else BotUnblocked(), ctx)

    async def delivery_failed(
        self, tg_user_id: int, reason: Literal["forbidden", "rate_limited", "other"], template: str
    ) -> None:
        user_id, family_id = await self._identity.resolve_telegram(tg_user_id)
        async with self._db.transaction() as session:
            ctx = EventContext(Platform.TELEGRAM_BOT, user_id, family_id, app_version=self._app_version)
            self._tracker.track(session, BotMessageFailed(reason=reason, template=template), ctx)
