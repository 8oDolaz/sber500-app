"""Bot capture (SPEC screens G → H): a message becomes draft actions; confirmed drafts become tasks/events.

Propose → confirm (ARCHITECTURE §6.1, ADR #7): nothing is written until the user presses «Сохранить».
When the LLM is unavailable or finds nothing, the fallback draft offers to save the text as a task as-is.
"""

import uuid
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from typing import Any, Literal
from zoneinfo import ZoneInfo

import structlog
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from planner.domain.planning import CreatedVia, NewEvent, NewTask, PlanningError
from planner.infra.db import Database
from planner.infra.ids import new_id
from planner.modules.analytics.catalog import (
    CaptureFailed,
    CaptureReceived,
    DraftActionCancelled,
    DraftActionConfirmed,
    DraftActionCreated,
    DraftActionExpired,
    DraftActionRevised,
    Platform,
)
from planner.modules.analytics.tracker import EventContext, Tracker
from planner.modules.assistant.extraction import ExtractionContext, Extractor, InvalidOutput, to_command
from planner.modules.assistant.llm_gateway.port import (
    LLMBudgetExceeded,
    LLMError,
    LLMQuotaExceeded,
    LLMRateLimited,
    LLMTimeout,
)
from planner.modules.assistant.tables import DraftActionRow
from planner.modules.families.tables import MemberRow
from planner.modules.planning.service import Actor, PlanningService

log = structlog.get_logger(__name__)

DRAFT_TTL = timedelta(hours=24)
WEEKDAYS_SHORT = ["пн", "вт", "ср", "чт", "пт", "сб", "вс"]

Source = Literal["forwarded", "own"]
FailureReason = Literal["llm_budget", "llm_timeout", "llm_error", "invalid_output", "no_items"]


@dataclass(frozen=True, slots=True)
class Draft:
    id: uuid.UUID
    command: str
    summary: str
    raw: bool  # the "save as-is" fallback


@dataclass(frozen=True, slots=True)
class CaptureOutcome:
    drafts: list[Draft]
    failure: FailureReason | None = None  # set together with a single raw draft


@dataclass(frozen=True, slots=True)
class Resolution:
    status: Literal["done", "already", "gone"]  # gone: expired, cancelled, revised or not yours
    summary: str | None = None


def _payload(cmd: NewTask | NewEvent) -> dict[str, Any]:
    def iso(v: date | datetime | None) -> str | None:
        return v.isoformat() if v else None

    if isinstance(cmd, NewTask):
        return {
            "title": cmd.title,
            "due_date": iso(cmd.due_date),
            "due_at": iso(cmd.due_at),
            "assignee_hint": cmd.assignee_hint,
        }
    return {
        "title": cmd.title,
        "starts_at": iso(cmd.starts_at),
        "ends_at": iso(cmd.ends_at),
        "start_date": iso(cmd.start_date),
        "participants_hint": cmd.participants_hint,
    }


def _command(kind: str, p: dict[str, Any]) -> NewTask | NewEvent:
    def d(v: str | None) -> date | None:
        return date.fromisoformat(v) if v else None

    def dt(v: str | None) -> datetime | None:
        return datetime.fromisoformat(v) if v else None

    if kind == "create_task":
        return NewTask(
            p["title"], due_date=d(p.get("due_date")), due_at=dt(p.get("due_at")), assignee_hint=p.get("assignee_hint")
        )
    return NewEvent(
        p["title"],
        starts_at=dt(p.get("starts_at")),
        ends_at=dt(p.get("ends_at")),
        start_date=d(p.get("start_date")),
        participants_hint=p.get("participants_hint"),
    )


def summarize(cmd: NewTask | NewEvent, tz: str) -> str:
    """One line for the draft card, in the family's timezone."""
    zone = ZoneInfo(tz)

    def day(v: date) -> str:
        return f"{WEEKDAYS_SHORT[v.weekday()]} {v:%d.%m}"

    parts: list[str]
    if isinstance(cmd, NewTask):
        parts = [f"Задача: {cmd.title}"]
        if cmd.due_at:
            local = cmd.due_at.astimezone(zone)
            parts.append(f"до {day(local.date())} {local:%H:%M}")
        elif cmd.due_date:
            parts.append(f"до {day(cmd.due_date)}")
        if cmd.assignee_hint:
            parts.append(cmd.assignee_hint)
    else:
        parts = [f"Событие: {cmd.title}"]
        if cmd.starts_at:
            start = cmd.starts_at.astimezone(zone)
            when = f"{day(start.date())} в {start:%H:%M}"
            if cmd.ends_at:
                when += f"–{cmd.ends_at.astimezone(zone):%H:%M}"
            parts.append(when)
        elif cmd.start_date:
            parts.append(f"{day(cmd.start_date)}, весь день")
        if cmd.participants_hint:
            parts.append(cmd.participants_hint)
    return " · ".join(parts)[:400]


def _failure_reason(exc: Exception) -> FailureReason:
    if isinstance(exc, LLMBudgetExceeded | LLMQuotaExceeded):
        return "llm_budget"
    if isinstance(exc, LLMTimeout | LLMRateLimited):
        return "llm_timeout"
    if isinstance(exc, InvalidOutput):
        return "invalid_output"
    return "llm_error"


class CaptureService:
    def __init__(
        self, db: Database, tracker: Tracker, extractor: Extractor, planning: PlanningService, app_version: str
    ) -> None:
        self._db = db
        self._tracker = tracker
        self._extractor = extractor
        self._planning = planning
        self._app_version = app_version

    async def capture(
        self,
        *,
        user_id: uuid.UUID,
        family_id: uuid.UUID,
        text: str,
        source: Source,
        written_at: datetime,
        revision_of: uuid.UUID | None = None,
    ) -> CaptureOutcome:
        ctx = EventContext(Platform.TELEGRAM_BOT, user_id, family_id, app_version=self._app_version)
        async with self._db.sessions() as session:
            tz = await self._planning.family_timezone(session, family_id)
            names = list(
                (await session.scalars(select(MemberRow.display_name).where(MemberRow.family_id == family_id))).all()
            )
        if revision_of is None:
            async with self._db.transaction() as session:
                self._tracker.track(session, CaptureReceived(source=source, content_type="text"), ctx)

        ex_ctx = ExtractionContext(
            reference=written_at, timezone=tz, member_names=names, user_id=user_id, family_id=family_id
        )
        commands: list[NewTask | NewEvent] = []
        failure: FailureReason | None = None
        model: str | None = None
        try:
            result = await self._extractor.extract(text, ex_ctx)
            model = result.model
            for item in result.items:
                try:
                    commands.append(to_command(item, ex_ctx))
                except PlanningError as exc:
                    log.info("capture.item_skipped", error=str(exc))
            if not commands:
                failure = "no_items"
        except (LLMError, InvalidOutput) as exc:
            failure = _failure_reason(exc)
            log.warning("capture.extraction_failed", reason=failure, error=repr(exc)[:300])

        if failure is not None:
            model = None
            commands = [NewTask(text.splitlines()[0] if text.strip() else text)]

        async with self._db.transaction() as session:
            if failure is not None:
                self._tracker.track(session, CaptureFailed(reason=failure), ctx)
            drafts = [
                self._add_draft(
                    session, ctx, cmd, tz, source=source, source_text=text, model=model, revision_of=revision_of
                )
                for cmd in commands
            ]
        return CaptureOutcome(drafts=drafts, failure=failure)

    def _add_draft(
        self,
        session: AsyncSession,
        ctx: EventContext,
        cmd: NewTask | NewEvent,
        tz: str,
        *,
        source: Source,
        source_text: str,
        model: str | None,
        revision_of: uuid.UUID | None,
    ) -> Draft:
        command = "create_task" if isinstance(cmd, NewTask) else "create_event"
        assert ctx.family_id is not None and ctx.user_id is not None
        row = DraftActionRow(
            id=new_id(),
            family_id=ctx.family_id,
            user_id=ctx.user_id,
            command=command,
            payload=_payload(cmd),
            summary=summarize(cmd, tz),
            source=source,
            source_text=source_text,
            model=model,
            status="pending",
            revision_of=revision_of,
            expires_at=datetime.now(UTC) + DRAFT_TTL,
        )
        session.add(row)
        self._tracker.track(
            session, DraftActionCreated(draft_id=row.id, command=command, source=source, model=model), ctx
        )
        return Draft(row.id, command, row.summary, raw=model is None)

    async def record_unsupported(
        self,
        *,
        user_id: uuid.UUID,
        family_id: uuid.UUID,
        source: Source,
        content_type: Literal["photo", "voice", "other"],
    ) -> None:
        """Photos/voice aren't understood yet; count them to see the demand."""
        async with self._db.transaction() as session:
            self._tracker.track(
                session,
                CaptureReceived(source=source, content_type=content_type),
                EventContext(Platform.TELEGRAM_BOT, user_id, family_id, app_version=self._app_version),
            )

    async def confirm(self, draft_id: uuid.UUID, user_id: uuid.UUID) -> Resolution:
        """«Сохранить». Idempotent for double taps."""
        async with self._db.transaction() as session:
            row = await self._pending(session, draft_id, user_id)
            if row is None or row.status != "pending":
                already = row is not None and row.status == "confirmed"
                return Resolution("already" if already else "gone", row.summary if row else None)
            actor = Actor(user_id, row.family_id, Platform.TELEGRAM_BOT)
            via = CreatedVia.BOT_DRAFT if row.model else CreatedVia.BOT_RAW
            cmd = _command(row.command, row.payload)
            if isinstance(cmd, NewTask):
                created = await self._planning.create_task(session, actor, cmd, via, row.source_text)
            else:
                created = await self._planning.create_event(session, actor, cmd, via, row.source_text)
            row.status, row.result_id, row.resolved_at = "confirmed", created.id, datetime.now(UTC)
            self._tracker.track(
                session,
                DraftActionConfirmed(draft_id=row.id, latency_s=self._latency(row)),
                EventContext(Platform.TELEGRAM_BOT, user_id, row.family_id, app_version=self._app_version),
            )
            return Resolution("done", row.summary)

    async def cancel(self, draft_id: uuid.UUID, user_id: uuid.UUID) -> Resolution:
        async with self._db.transaction() as session:
            row = await self._pending(session, draft_id, user_id)
            if row is None or row.status != "pending":
                return Resolution("gone", row.summary if row else None)
            row.status, row.resolved_at = "cancelled", datetime.now(UTC)
            self._tracker.track(
                session,
                DraftActionCancelled(draft_id=row.id, latency_s=self._latency(row)),
                EventContext(Platform.TELEGRAM_BOT, user_id, row.family_id, app_version=self._app_version),
            )
            return Resolution("done", row.summary)

    async def can_revise(self, draft_id: uuid.UUID, user_id: uuid.UUID) -> bool:
        async with self._db.sessions() as session:
            row = await session.get(DraftActionRow, draft_id)
            return row is not None and row.user_id == user_id and row.status == "pending"

    async def revise(self, draft_id: uuid.UUID, user_id: uuid.UUID, new_text: str) -> CaptureOutcome | None:
        """«Изменить»: the user's correction replaces the draft with freshly extracted ones."""
        async with self._db.transaction() as session:
            row = await self._pending(session, draft_id, user_id)
            if row is None or row.status != "pending":
                return None
            row.status, row.resolved_at = "revised", datetime.now(UTC)
            family_id, source = row.family_id, row.source
            self._tracker.track(
                session,
                DraftActionRevised(draft_id=row.id, latency_s=self._latency(row)),
                EventContext(Platform.TELEGRAM_BOT, user_id, family_id, app_version=self._app_version),
            )
        return await self.capture(
            user_id=user_id,
            family_id=family_id,
            text=new_text,
            source=source,  # type: ignore[arg-type]
            written_at=datetime.now(UTC),
            revision_of=draft_id,
        )

    async def expire(self, now: datetime | None = None) -> int:
        """Worker job: pending drafts older than the TTL expire (the denominator for confirm rates)."""
        now = now or datetime.now(UTC)
        async with self._db.transaction() as session:
            rows = (
                await session.execute(
                    update(DraftActionRow)
                    .where(DraftActionRow.status == "pending", DraftActionRow.expires_at <= now)
                    .values(status="expired", resolved_at=now)
                    .returning(DraftActionRow.id, DraftActionRow.user_id, DraftActionRow.family_id)
                )
            ).all()
            for r in rows:
                self._tracker.track(
                    session,
                    DraftActionExpired(draft_id=r.id),
                    EventContext(Platform.SERVER, r.user_id, r.family_id, app_version=self._app_version),
                )
        return len(rows)

    @staticmethod
    async def _pending(session: AsyncSession, draft_id: uuid.UUID, user_id: uuid.UUID) -> DraftActionRow | None:
        row = await session.scalar(select(DraftActionRow).where(DraftActionRow.id == draft_id).with_for_update())
        if row is None or row.user_id != user_id:
            return None
        if row.status == "pending" and row.expires_at <= datetime.now(UTC):
            return None  # the expiry job will record it
        return row

    @staticmethod
    def _latency(row: DraftActionRow) -> int:
        return int((datetime.now(UTC) - row.created_at).total_seconds())
