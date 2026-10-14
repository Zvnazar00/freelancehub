"""Invoices and payments (docs/architecture.md §8, docs/database.md §3.9).

Lifecycle:  draft ──send──▶ sent ──payments == total──▶ paid
              │               │ ◀──delete a payment─────┘
            delete          void (only without payments; releases the entries)

* A time entry can be on at most one invoice (``time_entries.invoice_id``). While it is there — draft
  included — it is locked: editing or deleting it returns ENTRY_LOCKED, so line amounts never drift.
* Time lines copy the entry's own rounded ``billable_amount``; custom lines are quantity * unit price
  (half-up). Tax is computed once on the subtotal. Totals are sums of the line amounts.
* Numbers (``INV-YYYY-NNNN``) are assigned on send under the per-user lock: drafts can be deleted
  freely, issued invoices can only be voided, so issued numbers never have gaps or duplicates.
* Every mutation takes the per-user lock first (the same one timer commands use), which serialises
  numbering, entry claiming and payment totals for one user.
"""

import uuid
from datetime import date, datetime, timedelta
from decimal import Decimal
from typing import Any
from zoneinfo import ZoneInfo

from sqlalchemy.orm import Session

from app.core.clock import Clock
from app.core.errors import AppError, Conflict, NotFound, ValidationFailed
from app.core.pagination import cursor_uuid, decode_cursor, encode_cursor
from app.models import Client, Invoice, InvoiceItem, Payment, Project, TimeEntry, User
from app.models.enums import InvoiceItemKind, InvoiceStatus, TimeEntryStatus
from app.repositories import invoices as repo
from app.repositories import time_entries as entries_repo
from app.schemas.invoices import (
    BillableEntries,
    BillableTotals,
    BillTo,
    CustomItemIn,
    InvoiceClientRef,
    InvoiceCreate,
    InvoiceItemOut,
    InvoiceOut,
    InvoicePage,
    InvoiceSummaryOut,
    InvoiceUpdate,
    PaymentCreate,
    PaymentOut,
    PaymentStatus,
)
from app.services import time_entries as entries_service
from app.services.money import ZERO, hours_quantity, line_amount, money_sum, tax_for

DEFAULT_DUE_DAYS = 14
MAX_BILLABLE_ENTRIES = 1000


def local_today(user: User, now: datetime) -> date:
    return now.astimezone(ZoneInfo(user.timezone)).date()


def _lock(db: Session, user: User, clock: Clock) -> datetime:
    entries_repo.lock_user(db, user.id)
    return clock()


def _owned_client(db: Session, user: User, client_id: uuid.UUID) -> Client:
    client = db.get(Client, client_id)
    if client is None or client.user_id != user.id:
        raise NotFound("Client not found.")
    return client


def _get(db: Session, user: User, invoice_id: uuid.UUID, *, for_update: bool = False) -> Invoice:
    invoice = repo.get_invoice(db, user.id, invoice_id, for_update=for_update)
    if invoice is None:
        raise NotFound("Invoice not found.")
    return invoice


def _check_version(db: Session, user: User, invoice: Invoice, version: int | None, now: datetime) -> None:
    if version is not None and version != invoice.version:
        raise Conflict(
            "The invoice was changed elsewhere. Reload and try again.",
            code="VERSION_CONFLICT",
            context={"current": serialize(db, user, [invoice], now, full=True)[0].model_dump(mode="json")},
        )


def _require_draft(invoice: Invoice) -> None:
    if invoice.status is not InvoiceStatus.draft:
        raise Conflict("Only draft invoices can be changed.", code="INVALID_TRANSITION")


def _amount_paid(invoice: Invoice) -> Decimal:
    return money_sum(p.amount for p in invoice.payments)


# ---------------------------------------------------------------- lines


def _line_description(project: Project, task_title: str | None, text: str) -> str:
    head = f"{project.name} · {task_title}" if task_title else project.name
    return (f"{head} — {text}" if text else head)[:500]


def _time_lines(
    db: Session, user: User, invoice: Invoice, entry_ids: list[uuid.UUID]
) -> tuple[list[InvoiceItem], list[TimeEntry]]:
    """Validates and locks the entries, then builds one line per entry (chronological)."""
    rows = repo.entries_for_invoice(db, user.id, entry_ids)
    found = {e.id for e, _ in rows}
    missing = [str(i) for i in entry_ids if i not in found]
    if missing:
        raise _entries_error("Some time entries do not exist.", "not_found", missing)

    taken = [str(e.id) for e, _ in rows if e.invoice_id not in (None, invoice.id)]
    if taken:
        raise Conflict(
            "Some time entries are already on another invoice.",
            code="ENTRY_ALREADY_INVOICED",
            context={"time_entry_ids": taken},
        )
    other_client = [str(e.id) for e, p in rows if p.client_id != invoice.client_id]
    if other_client:
        raise _entries_error("Some time entries belong to another client.", "other_client", other_client)
    not_billable = [
        str(e.id)
        for e, _ in rows
        if e.status is not TimeEntryStatus.stopped or not e.billable or e.billable_amount is None
    ]
    if not_billable:
        raise _entries_error(
            "Only stopped, billable entries with an hourly rate can be invoiced.", "not_billable", not_billable
        )
    wrong_currency = [str(e.id) for e, _ in rows if e.currency != invoice.currency]
    if wrong_currency:
        raise ValidationFailed(
            f"All entries must be in the invoice currency ({invoice.currency}).",
            field="time_entry_ids",
            code="currency_mismatch",
            problem_code="CURRENCY_MISMATCH",
        )

    tasks = entries_repo.task_refs(db, user.id, {e.task_id for e, _ in rows if e.task_id})
    zone = ZoneInfo(user.timezone)
    lines: list[InvoiceItem] = []
    for entry, project in rows:
        assert entry.duration_seconds is not None and entry.billable_amount is not None  # noqa: S101 - checked
        assert entry.hourly_rate_snapshot is not None  # noqa: S101 - a priced entry always has a rate
        task = tasks.get(entry.task_id) if entry.task_id else None
        lines.append(
            InvoiceItem(
                kind=InvoiceItemKind.time,
                time_entry_id=entry.id,
                description=_line_description(project, task.title if task else None, entry.description),
                service_date=entry.started_at.astimezone(zone).date(),
                duration_seconds=entry.duration_seconds,
                quantity=hours_quantity(entry.duration_seconds),
                unit_price=entry.hourly_rate_snapshot,
                amount=entry.billable_amount,
                position=0,
            )
        )
    return lines, [e for e, _ in rows]


def _entries_error(detail: str, code: str, ids: list[str]) -> ValidationFailed:
    error = ValidationFailed(detail, field="time_entry_ids", code=code, problem_code="INVALID_INVOICE_ENTRIES")
    error.context = {**(error.context or {}), "time_entry_ids": ids}
    return error


def _custom_lines(items: list[CustomItemIn]) -> list[InvoiceItem]:
    return [
        InvoiceItem(
            kind=InvoiceItemKind.custom,
            description=item.description,
            quantity=item.quantity,
            unit_price=item.unit_price,
            amount=line_amount(item.quantity, item.unit_price),
            position=0,
        )
        for item in items
    ]


def _set_lines(invoice: Invoice, time_lines: list[InvoiceItem], custom_lines: list[InvoiceItem]) -> None:
    lines = [*time_lines, *custom_lines]
    for position, line in enumerate(lines):
        line.position = position
    invoice.items = lines
    _recompute(invoice)


def _recompute(invoice: Invoice) -> None:
    invoice.subtotal = money_sum(line.amount for line in invoice.items)
    invoice.tax_amount = tax_for(invoice.subtotal, invoice.tax_rate)
    invoice.total = invoice.subtotal + invoice.tax_amount


def _claim(invoice: Invoice, entries: list[TimeEntry]) -> None:
    for entry in entries:
        if entry.invoice_id != invoice.id:
            entry.invoice_id = invoice.id
            entry.version += 1


# ---------------------------------------------------------------- commands


def create(db: Session, user: User, data: InvoiceCreate, clock: Clock) -> Invoice:
    now = _lock(db, user, clock)
    client = _owned_client(db, user, data.client_id)
    issue = data.issue_date or local_today(user, now)
    due = data.due_date or issue + timedelta(days=DEFAULT_DUE_DAYS)
    if due < issue:
        raise ValidationFailed("due_date must not be before issue_date.", field="due_date", code="due_before_issue")

    currency: str | None = data.currency
    if currency is None and data.time_entry_ids:
        currencies = {e.currency for e, _ in repo.entries_for_invoice(db, user.id, data.time_entry_ids)}
        currency = currencies.pop() if len(currencies) == 1 else None  # mixed → validated below
    invoice = Invoice(
        user_id=user.id,
        client_id=client.id,
        status=InvoiceStatus.draft,
        issue_date=issue,
        due_date=due,
        currency=currency or client.currency,
        tax_rate=data.tax_rate,
        notes=data.notes or None,
        version=1,
        created_at=now,  # from the injected clock: list order (created_at, id) is then deterministic
        updated_at=now,
    )
    db.add(invoice)
    db.flush()
    time_lines, entries = _time_lines(db, user, invoice, data.time_entry_ids)
    _set_lines(invoice, time_lines, _custom_lines(data.items))
    _claim(invoice, entries)
    db.flush()
    return invoice


def update(db: Session, user: User, invoice_id: uuid.UUID, data: InvoiceUpdate, clock: Clock) -> Invoice:
    now = _lock(db, user, clock)
    invoice = _get(db, user, invoice_id, for_update=True)
    _check_version(db, user, invoice, data.version, now)
    _require_draft(invoice)

    issue = data.issue_date or invoice.issue_date
    due = data.due_date or invoice.due_date
    if due < issue:
        raise ValidationFailed("due_date must not be before issue_date.", field="due_date", code="due_before_issue")
    invoice.issue_date, invoice.due_date = issue, due
    if "notes" in data.model_fields_set:
        invoice.notes = data.notes or None
    if data.tax_rate is not None:
        invoice.tax_rate = data.tax_rate

    time_lines = [line for line in invoice.items if line.kind is InvoiceItemKind.time]
    custom_lines = [line for line in invoice.items if line.kind is InvoiceItemKind.custom]
    if data.time_entry_ids is not None:
        repo.release_entries(db, invoice.id, keep=data.time_entry_ids)
        time_lines, entries = _time_lines(db, user, invoice, data.time_entry_ids)
        _claim(invoice, entries)
    if data.items is not None:
        custom_lines = _custom_lines(data.items)
    _set_lines(invoice, time_lines, custom_lines)
    invoice.version += 1
    db.flush()
    return invoice


def delete(db: Session, user: User, invoice_id: uuid.UUID, clock: Clock) -> None:
    _lock(db, user, clock)
    invoice = _get(db, user, invoice_id, for_update=True)
    if invoice.status is not InvoiceStatus.draft:
        raise Conflict("Issued invoices cannot be deleted; void them instead.", code="INVALID_TRANSITION")
    repo.release_entries(db, invoice.id)
    db.delete(invoice)
    db.flush()


def send(db: Session, user: User, invoice_id: uuid.UUID, version: int | None, clock: Clock) -> Invoice:
    now = _lock(db, user, clock)
    invoice = _get(db, user, invoice_id, for_update=True)
    _check_version(db, user, invoice, version, now)
    if invoice.status is not InvoiceStatus.draft:
        raise Conflict("This invoice has already been sent.", code="INVALID_TRANSITION")
    if not invoice.items or invoice.total <= ZERO:
        raise ValidationFailed(
            "Add at least one line with a positive amount before sending.",
            field="items",
            code="empty",
            problem_code="INVOICE_EMPTY",
        )
    client = db.get(Client, invoice.client_id)
    assert client is not None  # noqa: S101 - composite FK guarantees it
    invoice.bill_to_name, invoice.bill_to_company, invoice.bill_to_email = client.name, client.company, client.email
    invoice.from_name, invoice.from_email = user.full_name, user.email
    invoice.number = repo.next_number(db, user.id, invoice.issue_date.year)
    invoice.status = InvoiceStatus.sent
    invoice.sent_at = now
    invoice.version += 1
    db.flush()
    return invoice


def void(db: Session, user: User, invoice_id: uuid.UUID, version: int | None, clock: Clock) -> Invoice:
    now = _lock(db, user, clock)
    invoice = _get(db, user, invoice_id, for_update=True)
    _check_version(db, user, invoice, version, now)
    if invoice.status is InvoiceStatus.draft:
        raise Conflict("Drafts are deleted, not voided.", code="INVALID_TRANSITION")
    if invoice.status is InvoiceStatus.void:
        raise Conflict("This invoice is already void.", code="INVALID_TRANSITION")
    if invoice.payments:
        raise Conflict("Delete the recorded payments before voiding this invoice.", code="INVOICE_HAS_PAYMENTS")
    repo.release_entries(db, invoice.id)
    invoice.status = InvoiceStatus.void
    invoice.voided_at = now
    invoice.version += 1
    db.flush()
    return invoice


def add_payment(db: Session, user: User, invoice_id: uuid.UUID, data: PaymentCreate, clock: Clock) -> Invoice:
    now = _lock(db, user, clock)
    invoice = _get(db, user, invoice_id, for_update=True)
    if invoice.status is InvoiceStatus.paid:
        raise Conflict("This invoice is already paid in full.", code="INVOICE_ALREADY_PAID")
    if invoice.status is not InvoiceStatus.sent:
        raise Conflict("Payments can only be recorded on sent invoices.", code="INVALID_TRANSITION")
    today = local_today(user, now)
    paid_on = data.paid_on or today
    if paid_on > today:
        raise ValidationFailed("The payment date cannot be in the future.", field="paid_on", code="future_date")

    due = invoice.total - _amount_paid(invoice)
    if data.amount > due:
        error = ValidationFailed(
            f"The payment exceeds the amount due ({due:.2f} {invoice.currency}).",
            field="amount",
            code="overpayment",
            problem_code="OVERPAYMENT",
        )
        error.context = {**(error.context or {}), "amount_due": f"{due:.2f}", "currency": invoice.currency}
        raise error
    payment = Payment(user_id=user.id, amount=data.amount, paid_on=paid_on, method=data.method, note=data.note or None)
    invoice.payments.append(payment)
    if data.amount == due:
        invoice.status = InvoiceStatus.paid
        invoice.paid_at = now
    invoice.version += 1
    db.flush()
    return invoice


def delete_payment(db: Session, user: User, invoice_id: uuid.UUID, payment_id: uuid.UUID, clock: Clock) -> Invoice:
    _lock(db, user, clock)
    invoice = _get(db, user, invoice_id, for_update=True)
    payment = next((p for p in invoice.payments if p.id == payment_id), None)
    if payment is None:
        raise NotFound("Payment not found.")
    invoice.payments.remove(payment)
    db.delete(payment)
    if invoice.status is InvoiceStatus.paid:
        invoice.status = InvoiceStatus.sent
        invoice.paid_at = None
    invoice.version += 1
    db.flush()
    return invoice


# ---------------------------------------------------------------- queries


def get(db: Session, user: User, invoice_id: uuid.UUID) -> Invoice:
    return _get(db, user, invoice_id)


def list_invoices(
    db: Session,
    user: User,
    *,
    status: str | None,
    client_id: uuid.UUID | None,
    cursor: str | None,
    limit: int,
    now: datetime,
) -> InvoicePage:
    after = None
    if cursor:
        raw_created, raw_id = decode_cursor(cursor, 2)
        try:
            after = (datetime.fromisoformat(raw_created), cursor_uuid(raw_id))
        except ValueError as exc:
            raise AppError("Malformed cursor.", code="BAD_REQUEST") from exc
    rows = repo.list_invoices(
        db,
        user.id,
        status=status,
        client_id=client_id,
        today=local_today(user, now),
        after=after,
        limit=limit + 1,
    )
    page, has_more = rows[:limit], len(rows) > limit
    next_cursor = encode_cursor([page[-1].created_at.isoformat(), page[-1].id]) if has_more and page else None
    return InvoicePage(items=serialize(db, user, page, now, full=False), next_cursor=next_cursor)


def billable_entries(
    db: Session,
    user: User,
    client_id: uuid.UUID,
    *,
    day_from: date | None,
    day_to: date | None,
    now: datetime,
    invoice_id: uuid.UUID | None = None,
) -> BillableEntries:
    _owned_client(db, user, client_id)
    if invoice_id is not None:
        draft = _get(db, user, invoice_id)
        _require_draft(draft)
        if draft.client_id != client_id:
            raise ValidationFailed("The invoice belongs to another client.", field="invoice_id", code="client_mismatch")
    filters: dict[str, Any] = {}
    if day_from or day_to:
        today = local_today(user, now)
        lo, hi = day_from or date(1970, 1, 1), day_to or today
        if hi < lo:
            raise ValidationFailed("'to' must not be before 'from'.", field="to", code="invalid_range")
        filters["start"], filters["end"] = entries_service.local_day_bounds(lo, hi, user.timezone)
    rows = repo.billable_entries(
        db, user.id, client_id, filters, MAX_BILLABLE_ENTRIES + 1, include_invoice_id=invoice_id
    )
    rows, truncated = rows[:MAX_BILLABLE_ENTRIES], len(rows) > MAX_BILLABLE_ENTRIES
    totals: dict[str, BillableTotals] = {}
    for e in rows:
        t = totals.setdefault(e.currency, BillableTotals(currency=e.currency, entries=0, seconds=0, amount=ZERO))
        t.entries += 1
        t.seconds += e.duration_seconds or 0
        t.amount += e.billable_amount or ZERO
    return BillableEntries(
        items=entries_service.serialize(db, user, rows, now),
        totals=sorted(totals.values(), key=lambda t: (-t.amount, t.currency)),
        truncated=truncated,
    )


def payment_status(invoice: Invoice, paid: Decimal) -> PaymentStatus | None:
    if invoice.status in (InvoiceStatus.draft, InvoiceStatus.void):
        return None
    if invoice.status is InvoiceStatus.paid:
        return "paid"
    return "partial" if paid > ZERO else "unpaid"


def serialize(db: Session, user: User, invoices: list[Invoice], now: datetime, *, full: bool) -> list[Any]:
    today = local_today(user, now)
    clients = repo.client_names(db, user.id, {i.client_id for i in invoices})
    out: list[Any] = []
    for inv in invoices:
        client = clients[inv.client_id]
        paid = _amount_paid(inv)
        overdue = inv.status is InvoiceStatus.sent and inv.due_date < today
        due = ZERO if inv.status in (InvoiceStatus.draft, InvoiceStatus.void) else inv.total - paid
        fields: dict[str, Any] = {
            "id": inv.id,
            "number": inv.number,
            "status": inv.status,
            "payment_status": payment_status(inv, paid),
            "is_overdue": overdue,
            "days_overdue": (today - inv.due_date).days if overdue else 0,
            "client": InvoiceClientRef(id=client.id, name=client.name),
            "issue_date": inv.issue_date,
            "due_date": inv.due_date,
            "currency": inv.currency,
            "subtotal": inv.subtotal,
            "tax_rate": inv.tax_rate,
            "tax_amount": inv.tax_amount,
            "total": inv.total,
            "amount_paid": paid,
            "amount_due": due,
            "tracked_seconds": sum(line.duration_seconds or 0 for line in inv.items),
            "sent_at": inv.sent_at,
            "paid_at": inv.paid_at,
            "voided_at": inv.voided_at,
            "version": inv.version,
            "created_at": inv.created_at,
            "updated_at": inv.updated_at,
        }
        if not full:
            out.append(InvoiceSummaryOut(**fields))
            continue
        issued = inv.bill_to_name is not None
        out.append(
            InvoiceOut(
                **fields,
                bill_to=BillTo(
                    name=inv.bill_to_name if issued else client.name,
                    company=inv.bill_to_company if issued else client.company,
                    email=inv.bill_to_email if issued else client.email,
                ),
                from_name=inv.from_name if issued else user.full_name,
                from_email=inv.from_email if issued else user.email,
                notes=inv.notes,
                items=[InvoiceItemOut.model_validate(line) for line in inv.items],
                payments=[PaymentOut.model_validate(p) for p in inv.payments],
            )
        )
    return out


def one(db: Session, user: User, invoice: Invoice, now: datetime) -> InvoiceOut:
    db.refresh(invoice)
    result: InvoiceOut = serialize(db, user, [invoice], now, full=True)[0]
    return result
