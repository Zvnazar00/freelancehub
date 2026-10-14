import uuid
from datetime import date, datetime
from decimal import Decimal
from typing import Annotated, Literal

from pydantic import (
    AfterValidator,
    BeforeValidator,
    Field,
    PlainSerializer,
    StringConstraints,
    WithJsonSchema,
    model_validator,
)

from app.models.enums import InvoiceItemKind, InvoiceStatus, PaymentMethod
from app.schemas.common import Amount, Currency, Rate, ResponseModel, StrictModel, parse_money
from app.schemas.time_entries import TimeEntryOut

Notes = Annotated[str, StringConstraints(strip_whitespace=True, max_length=2000)]
LineText = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=500)]
PaymentNote = Annotated[str, StringConstraints(strip_whitespace=True, max_length=500)]


def _percent(value: Decimal) -> Decimal:
    if value > Decimal(100):
        raise ValueError("must be at most 100")
    return value


def _positive(value: Decimal) -> Decimal:
    if value <= 0:
        raise ValueError("must be greater than 0")
    if value > Decimal("99999.99"):
        raise ValueError("must be at most 99999.99")
    return value


_two_dp = PlainSerializer(lambda v: f"{v:.2f}", return_type=str, when_used="json")
_four_dp = PlainSerializer(lambda v: f"{v:.4f}", return_type=str, when_used="json")
_decimal_schema = WithJsonSchema({"type": "string", "examples": ["20.00"]})

TaxRate = Annotated[Decimal, BeforeValidator(parse_money), AfterValidator(_percent), _two_dp, _decimal_schema]
Quantity = Annotated[Decimal, BeforeValidator(parse_money), AfterValidator(_positive), _four_dp, _decimal_schema]
QuantityOut = Annotated[Decimal, _four_dp, _decimal_schema]
PositiveAmount = Annotated[Amount, AfterValidator(lambda v: _positive_amount(v))]


def _positive_amount(value: Decimal) -> Decimal:
    if value <= 0:
        raise ValueError("must be greater than 0")
    return value


# ---------- requests ----------


class CustomItemIn(StrictModel):
    description: LineText
    quantity: Quantity = Decimal(1)
    unit_price: Rate


class InvoiceCreate(StrictModel):
    client_id: uuid.UUID
    issue_date: date | None = Field(default=None, description="Defaults to today in the user's time zone")
    due_date: date | None = Field(default=None, description="Defaults to issue_date + 14 days")
    currency: Currency | None = Field(default=None, description="Defaults to the entries' currency, else the client's")
    tax_rate: TaxRate = Decimal(0)
    notes: Notes | None = None
    time_entry_ids: list[uuid.UUID] = Field(default_factory=list, max_length=500)
    items: list[CustomItemIn] = Field(default_factory=list, max_length=50)

    @model_validator(mode="after")
    def _check(self) -> "InvoiceCreate":
        if len(set(self.time_entry_ids)) != len(self.time_entry_ids):
            raise ValueError("time_entry_ids must be unique")
        if self.issue_date and self.due_date and self.due_date < self.issue_date:
            raise ValueError("due_date must not be before issue_date")
        return self


class InvoiceUpdate(StrictModel):
    version: int = Field(ge=1)
    issue_date: date | None = None
    due_date: date | None = None
    tax_rate: TaxRate | None = None
    notes: Notes | None = None
    time_entry_ids: list[uuid.UUID] | None = Field(default=None, max_length=500, description="Replaces the time lines")
    items: list[CustomItemIn] | None = Field(default=None, max_length=50, description="Replaces the custom lines")

    @model_validator(mode="after")
    def _check(self) -> "InvoiceUpdate":
        for field in ("issue_date", "due_date", "tax_rate", "time_entry_ids", "items"):
            if field in self.model_fields_set and getattr(self, field) is None:
                raise ValueError(f"{field} cannot be null")
        if self.time_entry_ids is not None and len(set(self.time_entry_ids)) != len(self.time_entry_ids):
            raise ValueError("time_entry_ids must be unique")
        return self


class VersionedCommand(StrictModel):
    version: int | None = Field(default=None, ge=1, description="If sent, the command fails on a stale version")


class PaymentCreate(StrictModel):
    amount: PositiveAmount
    paid_on: date | None = Field(default=None, description="Defaults to today in the user's time zone")
    method: PaymentMethod = PaymentMethod.bank_transfer
    note: PaymentNote | None = None


# ---------- responses ----------


class InvoiceItemOut(ResponseModel):
    id: uuid.UUID
    kind: InvoiceItemKind
    time_entry_id: uuid.UUID | None
    description: str
    service_date: date | None
    duration_seconds: int | None
    quantity: QuantityOut
    unit_price: Rate
    amount: Amount


class PaymentOut(ResponseModel):
    id: uuid.UUID
    amount: Amount
    paid_on: date
    method: PaymentMethod
    note: str | None
    created_at: datetime


class InvoiceClientRef(ResponseModel):
    id: uuid.UUID
    name: str


class BillTo(ResponseModel):
    name: str
    company: str | None
    email: str | None


PaymentStatus = Literal["unpaid", "partial", "paid"]


class InvoiceSummaryOut(ResponseModel):
    id: uuid.UUID
    number: str | None = Field(description="Assigned when the invoice is sent (INV-YYYY-NNNN); null for drafts")
    status: InvoiceStatus
    payment_status: PaymentStatus | None = Field(description="null for drafts and void invoices")
    is_overdue: bool = Field(description="Sent, not fully paid, and due before today (user time zone)")
    days_overdue: int
    client: InvoiceClientRef
    issue_date: date
    due_date: date
    currency: str
    subtotal: Amount
    tax_rate: TaxRate
    tax_amount: Amount
    total: Amount
    amount_paid: Amount
    amount_due: Amount
    tracked_seconds: int
    sent_at: datetime | None
    paid_at: datetime | None
    voided_at: datetime | None
    version: int
    created_at: datetime
    updated_at: datetime


class InvoiceOut(InvoiceSummaryOut):
    bill_to: BillTo
    from_name: str | None
    from_email: str | None
    notes: str | None
    items: list[InvoiceItemOut]
    payments: list[PaymentOut]


class InvoicePage(ResponseModel):
    items: list[InvoiceSummaryOut]
    next_cursor: str | None


class BillableTotals(ResponseModel):
    currency: str
    entries: int
    seconds: int
    amount: Amount


class BillableEntries(ResponseModel):
    items: list[TimeEntryOut]
    totals: list[BillableTotals]
    truncated: bool = Field(description="True when more entries exist than were returned (narrow the date range)")
