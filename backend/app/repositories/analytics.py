"""Aggregation queries for the dashboard and analytics. Every query is scoped by user_id.

Local-day bucketing happens in SQL with `timezone(:tz, started_at)::date`, so DST transitions are handled by
PostgreSQL's tz database; coarser buckets (week/month) are derived from local days in Python.
"""

import uuid
from datetime import date, datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import Date, case, cast, func, select
from sqlalchemy.orm import Session

from app.models import Client, Invoice, Payment, Project, Task, TimeEntry
from app.models.enums import InvoiceStatus, TimeEntryStatus
from app.repositories.invoices import not_on_issued_invoice

ISSUED = (InvoiceStatus.sent, InvoiceStatus.paid)


def _stopped(user_id: uuid.UUID, start: datetime | None = None, end: datetime | None = None) -> list[Any]:
    conditions: list[Any] = [TimeEntry.user_id == user_id, TimeEntry.status == TimeEntryStatus.stopped]
    if start is not None:
        conditions.append(TimeEntry.started_at >= start)
    if end is not None:
        conditions.append(TimeEntry.started_at < end)
    return conditions


_billable_seconds = func.coalesce(func.sum(case((TimeEntry.billable, TimeEntry.duration_seconds), else_=0)), 0)
_seconds = func.coalesce(func.sum(TimeEntry.duration_seconds), 0)
_amount = func.sum(TimeEntry.billable_amount)
# Seconds that actually earned money (billable AND priced) — the denominator of an effective hourly rate.
_priced_seconds = func.coalesce(
    func.sum(case((TimeEntry.billable_amount.is_not(None), TimeEntry.duration_seconds), else_=0)), 0
)


def daily(
    db: Session, user_id: uuid.UUID, tz: str, start: datetime, end: datetime
) -> list[tuple[date, str, int, int, int, Decimal | None, int]]:
    """(local day, currency, seconds, billable s, priced s, tracked amount, entries) for stopped entries."""
    day = cast(func.timezone(tz, TimeEntry.started_at), Date)
    stmt = (
        select(day, TimeEntry.currency, _seconds, _billable_seconds, _priced_seconds, _amount, func.count())
        .where(*_stopped(user_id, start, end))
        .group_by(day, TimeEntry.currency)
        .order_by(day)
    )
    return [(d, c, int(s), int(b), int(p), a, int(n)) for d, c, s, b, p, a, n in db.execute(stmt)]


def payments_daily(db: Session, user_id: uuid.UUID, lo: date, hi: date) -> list[tuple[date, str, Decimal]]:
    stmt = (
        select(Payment.paid_on, Invoice.currency, func.sum(Payment.amount))
        .join(Invoice, (Invoice.id == Payment.invoice_id) & (Invoice.user_id == Payment.user_id))
        .where(Payment.user_id == user_id, Payment.paid_on >= lo, Payment.paid_on <= hi)
        .group_by(Payment.paid_on, Invoice.currency)
    )
    return [(d, c, a) for d, c, a in db.execute(stmt)]


def invoiced_by_currency(db: Session, user_id: uuid.UUID, lo: date, hi: date) -> dict[str, Decimal]:
    stmt = (
        select(Invoice.currency, func.sum(Invoice.total))
        .where(
            Invoice.user_id == user_id,
            Invoice.status.in_(ISSUED),
            Invoice.issue_date >= lo,
            Invoice.issue_date <= hi,
        )
        .group_by(Invoice.currency)
    )
    return {c: a for c, a in db.execute(stmt)}


def unbilled_by_currency(db: Session, user_id: uuid.UUID) -> dict[str, Decimal]:
    stmt = (
        select(TimeEntry.currency, func.sum(TimeEntry.billable_amount))
        .where(*_stopped(user_id), TimeEntry.billable, TimeEntry.billable_amount.is_not(None), not_on_issued_invoice())
        .group_by(TimeEntry.currency)
    )
    return {c: a for c, a in db.execute(stmt) if a is not None}


def open_invoices(db: Session, user_id: uuid.UUID) -> list[tuple[str, date, Decimal, Decimal]]:
    """(currency, due date, total, paid) of every sent (open) invoice."""
    paid = (
        select(func.coalesce(func.sum(Payment.amount), 0))
        .where(Payment.invoice_id == Invoice.id)
        .correlate(Invoice)
        .scalar_subquery()
    )
    stmt = select(Invoice.currency, Invoice.due_date, Invoice.total, paid).where(
        Invoice.user_id == user_id, Invoice.status == InvoiceStatus.sent
    )
    return [(c, d, t, p) for c, d, t, p in db.execute(stmt)]


def invoice_status_counts(db: Session, user_id: uuid.UUID) -> dict[InvoiceStatus, int]:
    stmt = select(Invoice.status, func.count()).where(Invoice.user_id == user_id).group_by(Invoice.status)
    return {s: int(n) for s, n in db.execute(stmt)}


def by_project(
    db: Session, user_id: uuid.UUID, start: datetime, end: datetime
) -> list[tuple[Project, str, str, int, int, int, Decimal | None]]:
    """(project, client name, currency, seconds, billable s, priced s, amount) per project and currency."""
    stmt = (
        select(Project, Client.name, TimeEntry.currency, _seconds, _billable_seconds, _priced_seconds, _amount)
        .join(Project, (Project.id == TimeEntry.project_id) & (Project.user_id == TimeEntry.user_id))
        .join(Client, (Client.id == Project.client_id) & (Client.user_id == Project.user_id))
        .where(*_stopped(user_id, start, end))
        .group_by(Project.id, Client.name, TimeEntry.currency)
    )
    return [(p, cn, c, int(s), int(b), int(ps), a) for p, cn, c, s, b, ps, a in db.execute(stmt)]


def by_client(
    db: Session, user_id: uuid.UUID, start: datetime, end: datetime
) -> list[tuple[Client, str, int, int, int, Decimal | None]]:
    stmt = (
        select(Client, TimeEntry.currency, _seconds, _billable_seconds, _priced_seconds, _amount)
        .join(Project, (Project.id == TimeEntry.project_id) & (Project.user_id == TimeEntry.user_id))
        .join(Client, (Client.id == Project.client_id) & (Client.user_id == Project.user_id))
        .where(*_stopped(user_id, start, end))
        .group_by(Client.id, TimeEntry.currency)
    )
    return [(cl, c, int(s), int(b), int(ps), a) for cl, c, s, b, ps, a in db.execute(stmt)]


def project_seconds_all_time(db: Session, user_id: uuid.UUID, project_ids: list[uuid.UUID]) -> dict[uuid.UUID, int]:
    if not project_ids:
        return {}
    stmt = (
        select(TimeEntry.project_id, _seconds)
        .where(*_stopped(user_id), TimeEntry.project_id.in_(project_ids))
        .group_by(TimeEntry.project_id)
    )
    return {p: int(s or 0) for p, s in db.execute(stmt)}


def project_money(
    db: Session, user_id: uuid.UUID, project_id: uuid.UUID
) -> list[tuple[str, int, int, int, int, Decimal | None, Decimal | None, Any, Any]]:
    """Per currency: seconds, billable s, priced s, entries, tracked, unbilled, first start, last start."""
    unbilled = func.sum(case((not_on_issued_invoice(), TimeEntry.billable_amount)))
    stmt = (
        select(
            TimeEntry.currency,
            _seconds,
            _billable_seconds,
            _priced_seconds,
            func.count(),
            _amount,
            unbilled,
            func.min(TimeEntry.started_at),
            func.max(TimeEntry.started_at),
        )
        .where(*_stopped(user_id), TimeEntry.project_id == project_id)
        .group_by(TimeEntry.currency)
    )
    return [(c, int(s), int(b), int(ps), int(n), a, u, lo, hi) for c, s, b, ps, n, a, u, lo, hi in db.execute(stmt)]


def project_by_task(
    db: Session, user_id: uuid.UUID, project_id: uuid.UUID
) -> list[tuple[uuid.UUID | None, str | None, str, int, Decimal | None]]:
    stmt = (
        select(TimeEntry.task_id, Task.title, TimeEntry.currency, _seconds, _amount)
        .outerjoin(Task, Task.id == TimeEntry.task_id)
        .where(*_stopped(user_id), TimeEntry.project_id == project_id)
        .group_by(TimeEntry.task_id, Task.title, TimeEntry.currency)
    )
    return [(t, title, c, int(s or 0), a) for t, title, c, s, a in db.execute(stmt)]


def project_seconds_since(db: Session, user_id: uuid.UUID, project_id: uuid.UUID, start: datetime) -> int:
    stmt = select(_seconds).where(*_stopped(user_id, start), TimeEntry.project_id == project_id)
    return int(db.scalar(stmt) or 0)
