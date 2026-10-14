"""CSV exports (docs/api.md §4.9).

* UTF-8 with a BOM so Excel opens Cyrillic and accented names correctly; RFC 4180 quoting via `csv`.
* Times are rendered in the user's time zone; durations both as hours (2 dp) and exact seconds.
* Money comes straight from the stored Decimal snapshots (never recomputed, never float).
* Formula-injection guard: free-text cells starting with = + - @ TAB CR get a leading apostrophe.
* Bounded to one year per request, so the file is built in memory (no long-lived DB session while streaming).
"""

import csv
import io
import uuid
from datetime import date, datetime
from decimal import ROUND_HALF_UP, Decimal
from typing import Any
from zoneinfo import ZoneInfo

from sqlalchemy import select
from sqlalchemy.orm import Session, aliased

from app.core.errors import ValidationFailed
from app.models import Client, Invoice, Project, Task, TimeEntry, User
from app.models.enums import InvoiceStatus, TimeEntryStatus
from app.repositories import invoices as invoices_repo
from app.services import time_entries as entries_service
from app.services.invoices import local_today, payment_status
from app.services.money import money_sum

MAX_RANGE_DAYS = 366
_DANGEROUS = ("=", "+", "-", "@", "\t", "\r")


def safe_text(value: str | None) -> str:
    if not value:
        return ""
    return f"'{value}" if value.startswith(_DANGEROUS) else value


def _range(user: User, day_from: date | None, day_to: date | None, now: datetime) -> tuple[date, date]:
    today = local_today(user, now)
    hi = day_to or today
    lo = day_from or hi.replace(day=1)
    if hi < lo:
        raise ValidationFailed("'to' must not be before 'from'.", field="to", code="invalid_range")
    if (hi - lo).days >= MAX_RANGE_DAYS:
        raise ValidationFailed("Exports are limited to one year.", field="to", code="range_too_long")
    return lo, hi


def _csv(header: list[str], rows: list[list[Any]]) -> bytes:
    buffer = io.StringIO()
    writer = csv.writer(buffer, lineterminator="\r\n")
    writer.writerow(header)
    writer.writerows(rows)
    return ("﻿" + buffer.getvalue()).encode("utf-8")


TIME_ENTRY_COLUMNS = [
    "date",
    "start",
    "end",
    "duration_hours",
    "duration_seconds",
    "client",
    "project",
    "task",
    "description",
    "billable",
    "rate",
    "currency",
    "amount",
    "billing_status",
    "invoice_number",
]


def time_entries_csv(
    db: Session,
    user: User,
    *,
    day_from: date | None,
    day_to: date | None,
    project_id: uuid.UUID | None,
    client_id: uuid.UUID | None,
    now: datetime,
) -> tuple[bytes, str]:
    lo, hi = _range(user, day_from, day_to, now)
    start, end = entries_service.local_day_bounds(lo, hi, user.timezone)
    zone = ZoneInfo(user.timezone)
    task = aliased(Task)
    stmt = (
        select(TimeEntry, Project.name, Client.name, task.title, Invoice.number, Invoice.status)
        .join(Project, (Project.id == TimeEntry.project_id) & (Project.user_id == TimeEntry.user_id))
        .join(Client, (Client.id == Project.client_id) & (Client.user_id == Project.user_id))
        .outerjoin(task, task.id == TimeEntry.task_id)
        .outerjoin(Invoice, Invoice.id == TimeEntry.invoice_id)
        .where(
            TimeEntry.user_id == user.id,
            TimeEntry.status == TimeEntryStatus.stopped,
            TimeEntry.started_at >= start,
            TimeEntry.started_at < end,
        )
        .order_by(TimeEntry.started_at, TimeEntry.id)
    )
    if project_id:
        stmt = stmt.where(TimeEntry.project_id == project_id)
    if client_id:
        stmt = stmt.where(Project.client_id == client_id)

    rows: list[list[Any]] = []
    for entry, project_name, client_name, task_title, invoice_number, invoice_status in db.execute(stmt):
        local_start = entry.started_at.astimezone(zone)
        assert entry.ended_at is not None and entry.duration_seconds is not None  # noqa: S101 - stopped entries
        hours = (Decimal(entry.duration_seconds) / 3600).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
        if not entry.billable or entry.billable_amount is None:
            billing = "not_billable"
        elif invoice_status in (InvoiceStatus.sent, InvoiceStatus.paid):
            billing = "paid" if invoice_status is InvoiceStatus.paid else "invoiced"
        else:
            billing = "unbilled"
        issued = invoice_status in (InvoiceStatus.sent, InvoiceStatus.paid)
        rows.append(
            [
                local_start.date().isoformat(),
                local_start.strftime("%H:%M"),
                entry.ended_at.astimezone(zone).strftime("%H:%M"),
                f"{hours:.2f}",
                entry.duration_seconds,
                safe_text(client_name),
                safe_text(project_name),
                safe_text(task_title),
                safe_text(entry.description),
                "yes" if entry.billable else "no",
                f"{entry.hourly_rate_snapshot:.2f}" if entry.hourly_rate_snapshot is not None else "",
                entry.currency,
                f"{entry.billable_amount:.2f}" if entry.billable_amount is not None else "",
                billing,
                invoice_number if issued else "",
            ]
        )
    return _csv(TIME_ENTRY_COLUMNS, rows), f"time-entries_{lo.isoformat()}_{hi.isoformat()}.csv"


INVOICE_COLUMNS = [
    "number",
    "status",
    "payment_status",
    "overdue",
    "client",
    "issue_date",
    "due_date",
    "currency",
    "subtotal",
    "tax_rate",
    "tax_amount",
    "total",
    "paid",
    "due",
]


def invoices_csv(
    db: Session,
    user: User,
    *,
    day_from: date | None,
    day_to: date | None,
    now: datetime,
) -> tuple[bytes, str]:
    """Invoices by issue date in the range. Drafts are excluded: they are not documents yet."""
    lo, hi = _range(user, day_from, day_to, now)
    today = local_today(user, now)
    invoices = list(
        db.scalars(
            select(Invoice)
            .where(
                Invoice.user_id == user.id,
                Invoice.status != InvoiceStatus.draft,
                Invoice.issue_date >= lo,
                Invoice.issue_date <= hi,
            )
            .order_by(Invoice.issue_date, Invoice.number)
        )
    )
    clients = invoices_repo.client_names(db, user.id, {i.client_id for i in invoices})
    rows: list[list[Any]] = []
    for inv in invoices:
        paid = money_sum(p.amount for p in inv.payments)
        open_ = inv.status is InvoiceStatus.sent
        rows.append(
            [
                inv.number,
                inv.status.value,
                payment_status(inv, paid) or "",
                "yes" if open_ and inv.due_date < today else "no",
                safe_text(clients[inv.client_id].name),
                inv.issue_date.isoformat(),
                inv.due_date.isoformat(),
                inv.currency,
                f"{inv.subtotal:.2f}",
                f"{inv.tax_rate:.2f}",
                f"{inv.tax_amount:.2f}",
                f"{inv.total:.2f}",
                f"{paid:.2f}",
                f"{(inv.total - paid) if inv.status is not InvoiceStatus.void else Decimal(0):.2f}",
            ]
        )
    return _csv(INVOICE_COLUMNS, rows), f"invoices_{lo.isoformat()}_{hi.isoformat()}.csv"
