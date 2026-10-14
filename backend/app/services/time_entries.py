"""Time-tracking engine (docs/time-tracking.md).

Every command:
  1. locks the user row (`SELECT … FOR UPDATE`) so one user's timer commands are serialised;
  2. validates the transition against the state machine and the timestamp rules;
  3. flushes — PostgreSQL constraints are the last line of defence (one active entry, no overlaps);
  4. lets the caller commit (together with the idempotency record, in the same transaction).

Timestamps are authoritative UTC instants taken from the injected clock; clients may only supply
`at` for commands queued offline, and it is validated (future skew, ordering, max age).
"""

import uuid
from dataclasses import dataclass
from datetime import UTC, date, datetime, time, timedelta
from decimal import Decimal
from typing import Any, NoReturn
from zoneinfo import ZoneInfo

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.clock import Clock
from app.core.errors import AppError, Conflict, NotFound, ValidationFailed
from app.core.pagination import cursor_uuid, decode_cursor, encode_cursor
from app.models import Client, Project, Task, TimeEntry, TimeEntryPause, User
from app.models.enums import BillingType, EntrySource, RateSource, TimeEntryStatus
from app.repositories import time_entries as repo
from app.schemas.time_entries import (
    ActiveEntryUpdate,
    CurrencySummary,
    DayTotal,
    EntryPage,
    EntryUpdate,
    ManualEntryCreate,
    PauseOut,
    ProjectRef,
    TaskRef,
    TimeEntryOut,
    TimerCommand,
    TimerStart,
    TimerStop,
)
from app.services.money import amount_for
from app.services.timekeeping import Interval, clip_pauses, net_seconds

# ---- tunables (documented in docs/time-tracking.md) ----
CLOCK_SKEW_TOLERANCE = timedelta(seconds=60)
MAX_BACKDATE = timedelta(days=7)
MANUAL_MAX_DURATION = timedelta(hours=24)
MAX_HISTORY_RANGE_DAYS = 366


# ---------------------------------------------------------------- helpers


@dataclass(frozen=True)
class ResolvedRate:
    rate: Decimal | None
    currency: str
    source: RateSource


def resolve_rate(project: Project, client: Client | None, user: User) -> ResolvedRate:
    """project.hourly_rate → client.default_hourly_rate → user.default_hourly_rate → none (hourly projects only)."""
    if project.billing_type is not BillingType.hourly:
        return ResolvedRate(None, project.currency, RateSource.none)
    if project.hourly_rate is not None:
        return ResolvedRate(project.hourly_rate, project.currency, RateSource.project)
    if client is not None and client.default_hourly_rate is not None:
        return ResolvedRate(client.default_hourly_rate, client.currency, RateSource.client)
    if user.default_hourly_rate is not None:
        return ResolvedRate(user.default_hourly_rate, user.default_currency, RateSource.user)
    return ResolvedRate(None, project.currency, RateSource.none)


def _intervals(entry: TimeEntry) -> list[Interval]:
    return [Interval(p.paused_at, p.resumed_at) for p in entry.pauses]


def _last_transition(entry: TimeEntry) -> datetime:
    last = entry.started_at
    for p in entry.pauses:
        last = max(last, p.paused_at, p.resumed_at or p.paused_at)
    return last


def _timestamp_error(detail: str, code: str, *, field: str = "at") -> ValidationFailed:
    return ValidationFailed(detail, field=field, code=code, problem_code=code)


def effective_time(
    at: datetime | None, now: datetime, *, not_before: datetime | None = None, max_age: timedelta | None = None
) -> datetime:
    """Server time by default; a client `at` is accepted only within the documented bounds."""
    if at is None:
        moment = now
    else:
        at = at.astimezone(UTC)
        if at > now + CLOCK_SKEW_TOLERANCE:
            raise _timestamp_error("Timestamp is in the future.", "TIMESTAMP_IN_FUTURE", field="at")
        moment = min(at, now)  # small skew ahead of the server is clamped to server time
    if max_age is not None and moment < now - max_age:
        raise _timestamp_error("Timestamp is too old.", "TIMESTAMP_TOO_OLD", field="at")
    if not_before is not None and moment < not_before:
        raise _timestamp_error("Timestamp is earlier than the last timer change.", "TIMESTAMP_OUT_OF_ORDER", field="at")
    return moment


def _finalize(entry: TimeEntry, end: datetime) -> None:
    entry.duration_seconds = net_seconds(entry.started_at, end, _intervals(entry))
    entry.billable_amount = (
        amount_for(entry.duration_seconds, entry.hourly_rate_snapshot)
        if entry.billable and entry.hourly_rate_snapshot is not None
        else None
    )


def _flush(db: Session) -> None:
    """Flush, translating constraint violations into domain errors (defence in depth)."""
    try:
        db.flush()
    except IntegrityError as exc:
        constraint = getattr(getattr(exc.orig, "diag", None), "constraint_name", None)
        db.rollback()
        if constraint == "ux_time_entries_one_active":
            raise Conflict("Another timer is already active.", code="ACTIVE_TIMER_EXISTS") from exc
        if constraint == "ex_time_entries_no_overlap":
            raise Conflict("This time overlaps another entry.", code="TIME_OVERLAP") from exc
        if constraint == "ck_time_entries_manual_max_24h":
            raise ValidationFailed(
                "A manual entry can be at most 24 hours.", field="ended_at", code="duration_too_long"
            ) from exc
        raise


def _owned_project(db: Session, user: User, project_id: uuid.UUID) -> Project:
    project = db.get(Project, project_id)
    if project is None or project.user_id != user.id:
        raise NotFound("Project not found.")
    if project.archived_at is not None:
        raise Conflict("Archived projects cannot receive time.", code="PROJECT_ARCHIVED")
    return project


def _owned_task(db: Session, user: User, task_id: uuid.UUID, project_id: uuid.UUID) -> Task:
    task = db.get(Task, task_id)
    if task is None or task.user_id != user.id:
        raise NotFound("Task not found.")
    if task.project_id != project_id:
        raise ValidationFailed("The task belongs to another project.", field="task_id", code="task_project_mismatch")
    return task


def _overlap_guard(
    db: Session, user: User, start: datetime, end: datetime | None, exclude_id: uuid.UUID | None, now: datetime
) -> None:
    other = repo.find_overlap(db, user.id, start, end, exclude_id=exclude_id)
    if other is not None:
        raise Conflict(
            "This time overlaps another entry.",
            code="TIME_OVERLAP",
            context={"conflicting_entry": serialize(db, user, [other], now)[0].model_dump(mode="json")},
        )


def _active_conflict(db: Session, user: User, active: TimeEntry, now: datetime) -> NoReturn:
    raise Conflict(
        "Another timer is already active. Stop or discard it first.",
        code="ACTIVE_TIMER_EXISTS",
        context={"active_entry": serialize(db, user, [active], now)[0].model_dump(mode="json")},
    )


def _require_active(db: Session, user: User, entry_id: uuid.UUID, now: datetime) -> TimeEntry:
    entry = repo.get_entry(db, user.id, entry_id, for_update=True)
    if entry is None:
        raise NotFound("Time entry not found.")
    if not entry.is_active:
        active = repo.get_active(db, user.id)
        if active is not None:
            raise Conflict(
                "This entry is not the active timer.",
                code="TIMER_MISMATCH",
                context={"active_entry": serialize(db, user, [active], now)[0].model_dump(mode="json")},
            )
        raise Conflict("The timer for this entry is already stopped.", code="INVALID_TRANSITION")
    return entry


def serialize(db: Session, user: User, entries: list[TimeEntry], now: datetime) -> list[TimeEntryOut]:
    projects = repo.project_refs(db, user.id, {e.project_id for e in entries})
    tasks = repo.task_refs(db, user.id, {e.task_id for e in entries if e.task_id})
    out = []
    for e in entries:
        p = projects[e.project_id]
        t = tasks.get(e.task_id) if e.task_id else None
        elapsed = (
            e.duration_seconds if e.duration_seconds is not None else net_seconds(e.started_at, now, _intervals(e))
        )
        out.append(
            TimeEntryOut(
                id=e.id,
                project=ProjectRef(id=p.id, name=p.name, color=p.color),
                task=TaskRef(id=t.id, title=t.title) if t else None,
                description=e.description,
                source=e.source,
                status=e.status,
                started_at=e.started_at,
                ended_at=e.ended_at,
                pauses=[PauseOut(paused_at=x.paused_at, resumed_at=x.resumed_at) for x in e.pauses],
                duration_seconds=e.duration_seconds,
                elapsed_seconds=elapsed,
                billable=e.billable,
                hourly_rate=e.hourly_rate_snapshot,
                currency=e.currency,
                rate_source=e.rate_source,
                rate_corrected_at=e.rate_corrected_at,
                billable_amount=e.billable_amount,
                invoice_id=e.invoice_id,
                version=e.version,
                created_at=e.created_at,
                updated_at=e.updated_at,
            )
        )
    return out


def one(db: Session, user: User, entry: TimeEntry, now: datetime) -> TimeEntryOut:
    db.refresh(entry)  # server-side defaults (created_at/updated_at) and pause ordering
    return serialize(db, user, [entry], now)[0]


# ---------------------------------------------------------------- timer commands


def _lock(db: Session, user: User, clock: Clock) -> datetime:
    """Take the per-user lock, THEN read the clock: a command that waited for the lock must not get a
    timestamp earlier than the command that held it (that would look out of order)."""
    repo.lock_user(db, user.id)
    return clock()


def current(db: Session, user: User) -> TimeEntry | None:
    return repo.get_active(db, user.id)


def start(db: Session, user: User, data: TimerStart, clock: Clock) -> tuple[TimeEntry, bool]:
    """Returns (entry, created). Re-sending a start with an existing ID returns that entry (idempotent)."""
    now = _lock(db, user, clock)
    existing = db.get(TimeEntry, data.id)
    if existing is not None:
        if existing.user_id != user.id:
            raise Conflict("This entry ID is already in use.", code="ID_CONFLICT")
        return existing, False
    active = repo.get_active(db, user.id)
    if active is not None:
        _active_conflict(db, user, active, now)

    project = _owned_project(db, user, data.project_id)
    if data.task_id:
        _owned_task(db, user, data.task_id, project.id)
    started = effective_time(data.at, now, max_age=MAX_BACKDATE)
    _overlap_guard(db, user, started, None, None, now)

    rate = resolve_rate(project, db.get(Client, project.client_id), user)
    entry = TimeEntry(
        id=data.id,
        user_id=user.id,
        project_id=project.id,
        task_id=data.task_id,
        description=data.description,
        source=EntrySource.timer,
        status=TimeEntryStatus.running,
        started_at=started,
        billable=data.billable if data.billable is not None else project.billing_type is BillingType.hourly,
        hourly_rate_snapshot=rate.rate,
        currency=rate.currency,
        rate_source=rate.source,
        version=1,
    )
    db.add(entry)
    _flush(db)
    return entry, True


def pause(db: Session, user: User, entry_id: uuid.UUID, data: TimerCommand, clock: Clock) -> TimeEntry:
    now = _lock(db, user, clock)
    entry = _require_active(db, user, entry_id, now)
    if entry.status is not TimeEntryStatus.running:
        raise Conflict("The timer is already paused.", code="INVALID_TRANSITION")
    moment = effective_time(data.at, now, not_before=_last_transition(entry))
    entry.pauses.append(TimeEntryPause(paused_at=moment))
    entry.status = TimeEntryStatus.paused
    entry.version += 1
    _flush(db)
    return entry


def resume(db: Session, user: User, entry_id: uuid.UUID, data: TimerCommand, clock: Clock) -> TimeEntry:
    now = _lock(db, user, clock)
    entry = _require_active(db, user, entry_id, now)
    if entry.status is not TimeEntryStatus.paused:
        raise Conflict("The timer is not paused.", code="INVALID_TRANSITION")
    moment = effective_time(data.at, now, not_before=_last_transition(entry))
    open_pause = next(p for p in entry.pauses if p.resumed_at is None)
    open_pause.resumed_at = moment
    entry.status = TimeEntryStatus.running
    entry.version += 1
    _flush(db)
    return entry


def stop(db: Session, user: User, entry_id: uuid.UUID, data: TimerStop, clock: Clock) -> TimeEntry:
    now = _lock(db, user, clock)
    entry = _require_active(db, user, entry_id, now)
    moment = effective_time(data.at, now, not_before=_last_transition(entry))
    if moment <= entry.started_at:
        raise _timestamp_error("Stop time must be after the start.", "TIMESTAMP_OUT_OF_ORDER", field="at")
    for p in entry.pauses:
        if p.resumed_at is None:
            p.resumed_at = moment  # stopping while paused closes the pause at the stop time
    if data.description is not None:
        entry.description = data.description
    entry.ended_at = moment
    entry.status = TimeEntryStatus.stopped
    _finalize(entry, moment)
    entry.version += 1
    _flush(db)
    return entry


def discard(db: Session, user: User, entry_id: uuid.UUID, clock: Clock) -> None:
    now = _lock(db, user, clock)
    entry = _require_active(db, user, entry_id, now)
    db.delete(entry)
    _flush(db)


def update_active(db: Session, user: User, entry_id: uuid.UUID, data: ActiveEntryUpdate, clock: Clock) -> TimeEntry:
    now = _lock(db, user, clock)
    entry = _require_active(db, user, entry_id, now)
    changes = data.model_dump(exclude_unset=True)
    if "task_id" in changes and changes["task_id"] is not None:
        _owned_task(db, user, changes["task_id"], entry.project_id)
    if "started_at" in changes:
        first_pause = min((p.paused_at for p in entry.pauses), default=now)
        new_start = effective_time(changes.pop("started_at"), now, max_age=MAX_BACKDATE)
        if new_start > first_pause:
            raise _timestamp_error(
                "started_at must be before the first pause.", "TIMESTAMP_OUT_OF_ORDER", field="started_at"
            )
        _overlap_guard(db, user, new_start, None, entry.id, now)
        entry.started_at = new_start
    for field, value in changes.items():
        setattr(entry, field, value)
    entry.version += 1
    _flush(db)
    return entry


# ---------------------------------------------------------------- stopped entries


def create_manual(db: Session, user: User, data: ManualEntryCreate, clock: Clock) -> TimeEntry:
    now = _lock(db, user, clock)
    project = _owned_project(db, user, data.project_id)
    if data.task_id:
        _owned_task(db, user, data.task_id, project.id)
    start_at, end_at = data.started_at.astimezone(UTC), data.ended_at.astimezone(UTC)
    _validate_range(start_at, end_at, now, manual=True)
    _overlap_guard(db, user, start_at, end_at, None, now)
    rate = resolve_rate(project, db.get(Client, project.client_id), user)
    entry = TimeEntry(
        user_id=user.id,
        project_id=project.id,
        task_id=data.task_id,
        description=data.description,
        source=EntrySource.manual,
        status=TimeEntryStatus.stopped,
        started_at=start_at,
        ended_at=end_at,
        billable=data.billable if data.billable is not None else project.billing_type is BillingType.hourly,
        hourly_rate_snapshot=rate.rate,
        currency=rate.currency,
        rate_source=rate.source,
        version=1,
    )
    entry.pauses = []
    _finalize(entry, end_at)
    db.add(entry)
    _flush(db)
    return entry


def _validate_range(start_at: datetime, end_at: datetime, now: datetime, *, manual: bool) -> None:
    if end_at <= start_at:
        raise ValidationFailed("ended_at must be after started_at.", field="ended_at", code="end_before_start")
    if end_at > now + CLOCK_SKEW_TOLERANCE:
        raise _timestamp_error("Entries cannot end in the future.", "TIMESTAMP_IN_FUTURE", field="ended_at")
    # Real elapsed time (UTC), so a 25-hour DST day cannot sneak past the limit.
    if manual and end_at - start_at > MANUAL_MAX_DURATION:
        raise ValidationFailed("A manual entry can be at most 24 hours.", field="ended_at", code="duration_too_long")


def update_entry(db: Session, user: User, entry_id: uuid.UUID, data: EntryUpdate, clock: Clock) -> TimeEntry:
    now = _lock(db, user, clock)
    entry = repo.get_entry(db, user.id, entry_id, for_update=True)
    if entry is None:
        raise NotFound("Time entry not found.")
    # Permanent states first: an invoiced entry is locked whatever version the client holds (attaching it to an
    # invoice bumps the version, so checking the version first would hide the real reason behind VERSION_CONFLICT).
    _ensure_not_invoiced(entry)
    if entry.version != data.version:
        raise Conflict(
            "The entry was changed elsewhere. Reload and try again.",
            code="VERSION_CONFLICT",
            context={"current": serialize(db, user, [entry], now)[0].model_dump(mode="json")},
        )
    if entry.is_active:
        raise Conflict("Running or paused entries are changed through /timer.", code="INVALID_TRANSITION")

    changes = data.model_dump(exclude_unset=True, exclude={"version", "reprice"})
    project_id = changes.get("project_id", entry.project_id)
    project = _owned_project(db, user, project_id) if project_id != entry.project_id else db.get(Project, project_id)
    assert project is not None  # noqa: S101 - FK guarantees existence

    task_id = changes.get("task_id", entry.task_id if project_id == entry.project_id else None)
    if task_id is not None:
        _owned_task(db, user, task_id, project_id)

    assert entry.ended_at is not None  # noqa: S101 - stopped entries always have an end (CHECK constraint)
    start_at: datetime = changes.get("started_at", entry.started_at).astimezone(UTC)
    end_at: datetime = changes.get("ended_at", entry.ended_at).astimezone(UTC)
    _validate_range(start_at, end_at, now, manual=entry.source is EntrySource.manual)
    if (start_at, end_at) != (entry.started_at, entry.ended_at):
        _overlap_guard(db, user, start_at, end_at, entry.id, now)
        kept = clip_pauses(_intervals(entry), start_at, end_at)
        entry.pauses = [TimeEntryPause(paused_at=p.start, resumed_at=p.end) for p in kept]

    entry.project_id = project_id
    entry.task_id = task_id
    entry.started_at, entry.ended_at = start_at, end_at
    if "description" in changes:
        entry.description = changes["description"]
    if "billable" in changes:
        entry.billable = changes["billable"]
    if data.reprice:
        # Explicit correction workflow: the only way a stored rate snapshot changes.
        rate = resolve_rate(project, db.get(Client, project.client_id), user)
        entry.hourly_rate_snapshot, entry.currency, entry.rate_source = rate.rate, rate.currency, rate.source
        entry.rate_corrected_at = now
    _finalize(entry, end_at)
    entry.version += 1
    _flush(db)
    return entry


def _ensure_not_invoiced(entry: TimeEntry) -> None:
    """Invoiced amounts must never drift from their lines: an entry on any invoice (draft included) is frozen."""
    if entry.invoice_id is not None:
        raise Conflict(
            "This entry is on an invoice. Remove it from the draft (or void the invoice) to change it.",
            code="ENTRY_LOCKED",
            context={"invoice_id": str(entry.invoice_id)},
        )


def delete_entry(db: Session, user: User, entry_id: uuid.UUID) -> None:
    repo.lock_user(db, user.id)
    entry = repo.get_entry(db, user.id, entry_id, for_update=True)
    if entry is None:
        raise NotFound("Time entry not found.")
    if entry.is_active:
        raise Conflict("Active timers are discarded through /timer/{id}/discard.", code="INVALID_TRANSITION")
    _ensure_not_invoiced(entry)
    db.delete(entry)
    _flush(db)


def get_entry(db: Session, user: User, entry_id: uuid.UUID) -> TimeEntry:
    entry = repo.get_entry(db, user.id, entry_id)
    if entry is None:
        raise NotFound("Time entry not found.")
    return entry


# ---------------------------------------------------------------- history


def local_day_bounds(day_from: date, day_to: date, tz: str) -> tuple[datetime, datetime]:
    """[local midnight of day_from, local midnight after day_to) as UTC instants. DST-safe (23/25-hour days)."""
    zone = ZoneInfo(tz)
    start = datetime.combine(day_from, time.min, tzinfo=zone).astimezone(UTC)
    end = datetime.combine(day_to + timedelta(days=1), time.min, tzinfo=zone).astimezone(UTC)
    return start, end


def history(
    db: Session,
    user: User,
    *,
    day_from: date | None,
    day_to: date | None,
    project_id: uuid.UUID | None,
    client_id: uuid.UUID | None,
    task_id: uuid.UUID | None,
    billable: bool | None,
    cursor: str | None,
    limit: int,
    now: datetime,
) -> EntryPage:
    filters: dict[str, Any] = {
        "project_id": project_id,
        "client_id": client_id,
        "task_id": task_id,
        "billable": billable,
    }
    if day_from or day_to:
        local_today = now.astimezone(ZoneInfo(user.timezone)).date()
        lo, hi = day_from or (day_to or local_today), day_to or local_today
        if hi < lo:
            raise ValidationFailed("'to' must not be before 'from'.", field="to", code="invalid_range")
        if (hi - lo).days >= MAX_HISTORY_RANGE_DAYS:
            raise ValidationFailed("Range is limited to one year.", field="to", code="range_too_long")
        filters["start"], filters["end"] = local_day_bounds(lo, hi, user.timezone)

    after = None
    if cursor:
        raw_start, raw_id = decode_cursor(cursor, 2)
        try:
            after = (datetime.fromisoformat(raw_start), cursor_uuid(raw_id))
        except ValueError as exc:
            raise AppError("Malformed cursor.", code="BAD_REQUEST") from exc

    rows = repo.list_entries(db, user.id, filters, after=after, limit=limit + 1)
    page, has_more = rows[:limit], len(rows) > limit
    next_cursor = encode_cursor([page[-1].started_at.isoformat(), page[-1].id]) if has_more and page else None
    summary = [
        CurrencySummary(currency=c, seconds=int(s), billable_seconds=int(bs), amount=Decimal(a))
        for c, s, bs, a in repo.currency_summary(db, user.id, filters)
    ]
    days = [
        DayTotal(date=d, seconds=int(s or 0), entries=int(n))
        for d, s, n in repo.day_totals(db, user.id, filters, user.timezone)
    ]
    return EntryPage(
        items=serialize(db, user, page, now), next_cursor=next_cursor, summary=summary, days=days, server_time=now
    )
