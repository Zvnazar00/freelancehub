import uuid
from datetime import date
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, Header, Query, Response, status

from app.api.deps import Auth, DbSession
from app.api.idempotency import run_optionally_idempotent
from app.core.clock import Clock, get_clock
from app.core.pagination import DEFAULT_LIMIT, MAX_LIMIT
from app.schemas.invoices import (
    BillableEntries,
    InvoiceCreate,
    InvoiceOut,
    InvoicePage,
    InvoiceUpdate,
    PaymentCreate,
    VersionedCommand,
)
from app.services import invoices as service
from app.services.invoice_pdf import render_invoice_pdf

router = APIRouter(prefix="/invoices", tags=["invoices"])
Now = Annotated[Clock, Depends(get_clock)]
IdemKey = Annotated[str | None, Header(alias="Idempotency-Key", description="Recommended: retries are replayed")]
StatusFilter = Literal["draft", "sent", "overdue", "paid", "void"]


@router.get("")
def list_invoices(
    auth: Auth,
    db: DbSession,
    clock: Now,
    status_filter: Annotated[StatusFilter | None, Query(alias="status")] = None,
    client_id: uuid.UUID | None = None,
    cursor: Annotated[str | None, Query(max_length=500)] = None,
    limit: Annotated[int, Query(ge=1, le=MAX_LIMIT)] = DEFAULT_LIMIT,
) -> InvoicePage:
    return service.list_invoices(
        db, auth.user, status=status_filter, client_id=client_id, cursor=cursor, limit=limit, now=clock()
    )


@router.get("/billable-entries")
def billable_entries(
    auth: Auth,
    db: DbSession,
    clock: Now,
    client_id: uuid.UUID,
    day_from: Annotated[date | None, Query(alias="from")] = None,
    day_to: Annotated[date | None, Query(alias="to")] = None,
    invoice_id: Annotated[
        uuid.UUID | None, Query(description="A draft being edited: its own entries are included as well")
    ] = None,
) -> BillableEntries:
    """Stopped, billable, priced entries of a client that are not on any invoice yet (oldest first)."""
    return service.billable_entries(
        db, auth.user, client_id, day_from=day_from, day_to=day_to, now=clock(), invoice_id=invoice_id
    )


@router.post("", status_code=status.HTTP_201_CREATED, response_model=InvoiceOut)
def create_invoice(
    body: InvoiceCreate, auth: Auth, db: DbSession, clock: Now, idempotency_key: IdemKey = None
) -> Response:
    def mutation() -> tuple[int, InvoiceOut]:
        invoice = service.create(db, auth.user, body, clock)
        return 201, service.one(db, auth.user, invoice, clock())

    return run_optionally_idempotent(
        db, auth.user, idempotency_key, "POST /invoices", body.model_dump(mode="json"), clock(), mutation
    )


@router.get("/{invoice_id}")
def get_invoice(invoice_id: uuid.UUID, auth: Auth, db: DbSession, clock: Now) -> InvoiceOut:
    return service.one(db, auth.user, service.get(db, auth.user, invoice_id), clock())


@router.patch("/{invoice_id}")
def update_invoice(invoice_id: uuid.UUID, body: InvoiceUpdate, auth: Auth, db: DbSession, clock: Now) -> InvoiceOut:
    invoice = service.update(db, auth.user, invoice_id, body, clock)
    db.commit()
    return service.one(db, auth.user, invoice, clock())


@router.delete("/{invoice_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_invoice(invoice_id: uuid.UUID, auth: Auth, db: DbSession, clock: Now) -> Response:
    service.delete(db, auth.user, invoice_id, clock)
    db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post("/{invoice_id}/send")
def send_invoice(
    invoice_id: uuid.UUID, auth: Auth, db: DbSession, clock: Now, body: VersionedCommand | None = None
) -> InvoiceOut:
    invoice = service.send(db, auth.user, invoice_id, body.version if body else None, clock)
    db.commit()
    return service.one(db, auth.user, invoice, clock())


@router.post("/{invoice_id}/void")
def void_invoice(
    invoice_id: uuid.UUID, auth: Auth, db: DbSession, clock: Now, body: VersionedCommand | None = None
) -> InvoiceOut:
    invoice = service.void(db, auth.user, invoice_id, body.version if body else None, clock)
    db.commit()
    return service.one(db, auth.user, invoice, clock())


@router.post("/{invoice_id}/payments", status_code=status.HTTP_201_CREATED, response_model=InvoiceOut)
def add_payment(
    invoice_id: uuid.UUID, body: PaymentCreate, auth: Auth, db: DbSession, clock: Now, idempotency_key: IdemKey = None
) -> Response:
    def mutation() -> tuple[int, InvoiceOut]:
        invoice = service.add_payment(db, auth.user, invoice_id, body, clock)
        return 201, service.one(db, auth.user, invoice, clock())

    payload = {"invoice_id": str(invoice_id), **body.model_dump(mode="json")}
    return run_optionally_idempotent(
        db, auth.user, idempotency_key, "POST /invoices/payments", payload, clock(), mutation
    )


@router.delete("/{invoice_id}/payments/{payment_id}")
def delete_payment(invoice_id: uuid.UUID, payment_id: uuid.UUID, auth: Auth, db: DbSession, clock: Now) -> InvoiceOut:
    invoice = service.delete_payment(db, auth.user, invoice_id, payment_id, clock)
    db.commit()
    return service.one(db, auth.user, invoice, clock())


@router.get(
    "/{invoice_id}/pdf",
    response_class=Response,
    responses={200: {"content": {"application/pdf": {}}, "description": "Invoice PDF"}},
)
def invoice_pdf(invoice_id: uuid.UUID, auth: Auth, db: DbSession, clock: Now) -> Response:
    invoice = service.one(db, auth.user, service.get(db, auth.user, invoice_id), clock())
    name = invoice.number or f"draft-{str(invoice.id)[:8]}"
    return Response(
        content=render_invoice_pdf(invoice),
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="{name}.pdf"', "Cache-Control": "no-store"},
    )
