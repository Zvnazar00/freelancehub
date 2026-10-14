import uuid
from datetime import date, datetime
from typing import Any

from sqlalchemy import Date, case, cast, func, literal, select, tuple_
from sqlalchemy.dialects.postgresql import TSTZRANGE
from sqlalchemy.orm import Session

from app.models import Project, Task, TimeEntry, User
from app.models.enums import TimeEntryStatus
from app.models.time_entry import ACTIVE_STATUSES
from app.repositories.invoices import not_on_issued_invoice


def lock_user(db: Session, user_id: uuid.UUID) -> None:
    """Serialises every timer command of one user (row lock held until commit/rollback).

    FOR NO KEY UPDATE, not FOR UPDATE: inserting rows that reference users (idempotency keys, entries)
    takes FOR KEY SHARE on the same row, and FOR UPDATE would conflict with it and deadlock two
    concurrent requests. NO KEY UPDATE still conflicts with itself, so commands remain serialised.
    """
    db.execute(select(User.id).where(User.id == user_id).with_for_update(key_share=True))  # renders FOR NO KEY UPDATE


def get_entry(db: Session, user_id: uuid.UUID, entry_id: uuid.UUID, *, for_update: bool = False) -> TimeEntry | None:
    stmt = select(TimeEntry).where(TimeEntry.id == entry_id, TimeEntry.user_id == user_id)
    if for_update:
        stmt = stmt.with_for_update()
    return db.scalar(stmt.execution_options(populate_existing=True))


def get_active(db: Session, user_id: uuid.UUID) -> TimeEntry | None:
    return db.scalar(
        select(TimeEntry)
        .where(TimeEntry.user_id == user_id, TimeEntry.status.in_(ACTIVE_STATUSES))
        .execution_options(populate_existing=True)
    )


def find_overlap(
    db: Session, user_id: uuid.UUID, start: datetime, end: datetime | None, *, exclude_id: uuid.UUID | None = None
) -> TimeEntry | None:
    """First entry whose [started_at, ended_at) intersects [start, end). NULL end = open-ended."""
    own = func.tstzrange(TimeEntry.started_at, TimeEntry.ended_at, "[)")
    other = func.tstzrange(literal(start), literal(end, type_=TimeEntry.ended_at.type), "[)", type_=TSTZRANGE)
    stmt = select(TimeEntry).where(TimeEntry.user_id == user_id, own.op("&&")(other))
    if exclude_id:
        stmt = stmt.where(TimeEntry.id != exclude_id)
    return db.scalar(stmt.order_by(TimeEntry.started_at).limit(1))


def _filtered(stmt: Any, user_id: uuid.UUID, filters: dict[str, Any]) -> Any:
    stmt = stmt.where(TimeEntry.user_id == user_id)
    if filters.get("start"):
        stmt = stmt.where(TimeEntry.started_at >= filters["start"])
    if filters.get("end"):
        stmt = stmt.where(TimeEntry.started_at < filters["end"])
    if filters.get("project_id"):
        stmt = stmt.where(TimeEntry.project_id == filters["project_id"])
    if filters.get("task_id"):
        stmt = stmt.where(TimeEntry.task_id == filters["task_id"])
    if filters.get("billable") is not None:
        stmt = stmt.where(TimeEntry.billable.is_(filters["billable"]))
    if filters.get("client_id"):
        stmt = stmt.where(
            TimeEntry.project_id.in_(
                select(Project.id).where(Project.user_id == user_id, Project.client_id == filters["client_id"])
            )
        )
    return stmt


def list_entries(
    db: Session,
    user_id: uuid.UUID,
    filters: dict[str, Any],
    *,
    after: tuple[datetime, uuid.UUID] | None,
    limit: int,
) -> list[TimeEntry]:
    stmt = _filtered(select(TimeEntry), user_id, filters)
    if after:
        stmt = stmt.where(tuple_(TimeEntry.started_at, TimeEntry.id) < tuple_(after[0], after[1]))
    return list(db.scalars(stmt.order_by(TimeEntry.started_at.desc(), TimeEntry.id.desc()).limit(limit)))


def currency_summary(db: Session, user_id: uuid.UUID, filters: dict[str, Any]) -> list[tuple[str, int, int, Any]]:
    billable_seconds = func.sum(case((TimeEntry.billable, TimeEntry.duration_seconds), else_=0))
    stmt = _filtered(
        select(
            TimeEntry.currency,
            func.coalesce(func.sum(TimeEntry.duration_seconds), 0),
            func.coalesce(billable_seconds, 0),
            func.coalesce(func.sum(TimeEntry.billable_amount), 0),
        ),
        user_id,
        filters,
    ).where(TimeEntry.status == TimeEntryStatus.stopped)
    return [tuple(r) for r in db.execute(stmt.group_by(TimeEntry.currency).order_by(TimeEntry.currency))]


def day_totals(db: Session, user_id: uuid.UUID, filters: dict[str, Any], tz: str) -> list[tuple[date, int, int]]:
    """Stopped entries grouped by the local calendar date of started_at in the user's time zone."""
    local_day = cast(func.timezone(tz, TimeEntry.started_at), Date)
    stmt = _filtered(select(local_day, func.sum(TimeEntry.duration_seconds), func.count()), user_id, filters).where(
        TimeEntry.status == TimeEntryStatus.stopped
    )
    return [tuple(r) for r in db.execute(stmt.group_by(local_day).order_by(local_day))]


def project_refs(db: Session, user_id: uuid.UUID, ids: set[uuid.UUID]) -> dict[uuid.UUID, Project]:
    if not ids:
        return {}
    return {p.id: p for p in db.scalars(select(Project).where(Project.user_id == user_id, Project.id.in_(ids)))}


def task_refs(db: Session, user_id: uuid.UUID, ids: set[uuid.UUID]) -> dict[uuid.UUID, Task]:
    if not ids:
        return {}
    return {t.id: t for t in db.scalars(select(Task).where(Task.user_id == user_id, Task.id.in_(ids)))}


def project_has_entries(db: Session, user_id: uuid.UUID, project_id: uuid.UUID) -> bool:
    stmt = (
        select(func.count())
        .select_from(TimeEntry)
        .where(TimeEntry.user_id == user_id, TimeEntry.project_id == project_id)
    )
    return (db.scalar(stmt) or 0) > 0


def stopped_totals(
    db: Session,
    user_id: uuid.UUID,
    *,
    project_ids: list[uuid.UUID] | None = None,
    client_ids: list[uuid.UUID] | None = None,
) -> dict[uuid.UUID, tuple[int, dict[str, Any]]]:
    """Stopped-entry totals grouped by project or by client: {key: (seconds, {currency: unbilled amount})}.

    One grouped query for a whole page of projects/clients (no N+1). Amounts come from the per-entry
    rounded snapshots, so totals equal the sum of what each entry shows. Entries on a sent or paid
    invoice are no longer "unbilled" (their seconds still count as tracked).
    """
    unbilled = func.sum(case((not_on_issued_invoice(), TimeEntry.billable_amount)))
    if project_ids is not None:
        if not project_ids:
            return {}
        key = TimeEntry.project_id
        stmt = select(key, TimeEntry.currency, func.sum(TimeEntry.duration_seconds), unbilled)
        stmt = stmt.where(TimeEntry.project_id.in_(project_ids))
    else:
        if not client_ids:
            return {}
        key = Project.client_id
        stmt = (
            select(key, TimeEntry.currency, func.sum(TimeEntry.duration_seconds), unbilled)
            .join(Project, (Project.id == TimeEntry.project_id) & (Project.user_id == TimeEntry.user_id))
            .where(Project.client_id.in_(client_ids))
        )
    stmt = stmt.where(TimeEntry.user_id == user_id, TimeEntry.status == TimeEntryStatus.stopped)
    result: dict[uuid.UUID, tuple[int, dict[str, Any]]] = {}
    for owner, currency, seconds, amount in db.execute(stmt.group_by(key, TimeEntry.currency)):
        total, amounts = result.get(owner, (0, {}))
        if amount is not None:
            amounts[currency] = amount
        result[owner] = (total + int(seconds or 0), amounts)
    return result
