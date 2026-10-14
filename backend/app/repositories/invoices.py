import uuid
from datetime import date, datetime
from typing import Any

from sqlalchemy import ColumnElement, Integer, cast, func, or_, select, tuple_, update
from sqlalchemy.orm import Session

from app.models import Client, Invoice, Project, TimeEntry
from app.models.enums import InvoiceStatus, TimeEntryStatus

ISSUED = (InvoiceStatus.sent, InvoiceStatus.paid)


def not_on_issued_invoice() -> ColumnElement[bool]:
    """Unbilled = not attached to a sent/paid invoice. Entries reserved by a draft still count as unbilled."""
    return or_(
        TimeEntry.invoice_id.is_(None),
        TimeEntry.invoice_id.in_(select(Invoice.id).where(Invoice.status == InvoiceStatus.draft)),
    )


def get_invoice(db: Session, user_id: uuid.UUID, invoice_id: uuid.UUID, *, for_update: bool = False) -> Invoice | None:
    stmt = select(Invoice).where(Invoice.id == invoice_id, Invoice.user_id == user_id)
    if for_update:
        stmt = stmt.with_for_update()
    return db.scalar(stmt.execution_options(populate_existing=True))


def list_invoices(
    db: Session,
    user_id: uuid.UUID,
    *,
    status: str | None,
    client_id: uuid.UUID | None,
    today: date,
    after: tuple[datetime, uuid.UUID] | None,
    limit: int,
) -> list[Invoice]:
    stmt = select(Invoice).where(Invoice.user_id == user_id)
    if client_id:
        stmt = stmt.where(Invoice.client_id == client_id)
    if status == "overdue":
        stmt = stmt.where(Invoice.status == InvoiceStatus.sent, Invoice.due_date < today)
    elif status:
        stmt = stmt.where(Invoice.status == InvoiceStatus(status))
    if after:
        stmt = stmt.where(tuple_(Invoice.created_at, Invoice.id) < tuple_(after[0], after[1]))
    return list(db.scalars(stmt.order_by(Invoice.created_at.desc(), Invoice.id.desc()).limit(limit)))


def client_names(db: Session, user_id: uuid.UUID, ids: set[uuid.UUID]) -> dict[uuid.UUID, Client]:
    if not ids:
        return {}
    return {c.id: c for c in db.scalars(select(Client).where(Client.user_id == user_id, Client.id.in_(ids)))}


def next_number(db: Session, user_id: uuid.UUID, year: int) -> str:
    """INV-<year>-<seq>. Callers hold the per-user lock, so two sends can never pick the same number."""
    prefix = f"INV-{year}-"
    current = db.scalar(
        select(func.max(cast(func.split_part(Invoice.number, "-", 3), Integer))).where(
            Invoice.user_id == user_id, Invoice.number.like(f"{prefix}%")
        )
    )
    return f"{prefix}{(current or 0) + 1:04d}"


def entries_for_invoice(db: Session, user_id: uuid.UUID, entry_ids: list[uuid.UUID]) -> list[tuple[TimeEntry, Project]]:
    """Locks the candidate entries (FOR UPDATE OF time_entries) so two drafts cannot claim the same entry."""
    if not entry_ids:
        return []
    stmt = (
        select(TimeEntry, Project)
        .join(Project, (Project.id == TimeEntry.project_id) & (Project.user_id == TimeEntry.user_id))
        .where(TimeEntry.user_id == user_id, TimeEntry.id.in_(entry_ids))
        .order_by(TimeEntry.started_at, TimeEntry.id)
        .with_for_update(of=TimeEntry)
        .execution_options(populate_existing=True)
    )
    return [(e, p) for e, p in db.execute(stmt)]


def release_entries(db: Session, invoice_id: uuid.UUID, *, keep: list[uuid.UUID] | None = None) -> None:
    stmt = update(TimeEntry).where(TimeEntry.invoice_id == invoice_id)
    if keep:
        stmt = stmt.where(TimeEntry.id.not_in(keep))
    db.execute(
        stmt.values(invoice_id=None, version=TimeEntry.version + 1).execution_options(synchronize_session="fetch")
    )


def billable_entries(
    db: Session,
    user_id: uuid.UUID,
    client_id: uuid.UUID,
    filters: dict[str, Any],
    limit: int,
    *,
    include_invoice_id: uuid.UUID | None = None,
) -> list[TimeEntry]:
    """Stopped, billable, priced entries of one client that are on no invoice at all (drafts included).

    With ``include_invoice_id`` (a draft being edited) the entries already on that draft are returned too,
    whatever the date filters, so the editor can show them as selected.
    """
    free = TimeEntry.invoice_id.is_(None)
    if filters.get("start"):
        free = free & (TimeEntry.started_at >= filters["start"])
    if filters.get("end"):
        free = free & (TimeEntry.started_at < filters["end"])
    pool = or_(free, TimeEntry.invoice_id == include_invoice_id) if include_invoice_id else free
    stmt = (
        select(TimeEntry)
        .join(Project, (Project.id == TimeEntry.project_id) & (Project.user_id == TimeEntry.user_id))
        .where(
            TimeEntry.user_id == user_id,
            Project.client_id == client_id,
            TimeEntry.status == TimeEntryStatus.stopped,
            TimeEntry.billable.is_(True),
            TimeEntry.billable_amount.is_not(None),
            pool,
        )
    )
    return list(db.scalars(stmt.order_by(TimeEntry.started_at, TimeEntry.id).limit(limit)))
