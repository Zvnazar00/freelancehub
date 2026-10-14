"""Invoices, invoice lines and payments (docs/database.md §3.9).

Money states (architecture.md §8) are derived from these tables, never stored twice:
  * tracked / unbilled — stopped billable entries that are not on an issued (sent or paid) invoice;
  * invoiced           — totals of issued invoices;
  * received           — sum of payments;
  * outstanding        — invoiced - received for invoices that are still open.
"""

import uuid
from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import (
    CheckConstraint,
    Date,
    DateTime,
    Enum,
    ForeignKey,
    ForeignKeyConstraint,
    Index,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    func,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, Timestamps, UUIDPrimaryKey
from app.models.enums import InvoiceItemKind, InvoiceStatus, PaymentMethod
from app.models.user import CURRENCY_CHECK


def _enum(cls: type, name: str) -> Enum:
    return Enum(cls, name=name, values_callable=lambda e: [m.value for m in e])


class Invoice(UUIDPrimaryKey, Timestamps, Base):
    __tablename__ = "invoices"
    __table_args__ = (
        UniqueConstraint("id", "user_id", name="uq_invoices_id_user_id"),
        # Numbers are assigned on send, so drafts have none and issued numbers never have gaps.
        UniqueConstraint("user_id", "number", name="uq_invoices_user_number"),
        ForeignKeyConstraint(
            ["client_id", "user_id"],
            ["clients.id", "clients.user_id"],
            name="fk_invoices_client_owner",
            ondelete="RESTRICT",
        ),
        CheckConstraint(CURRENCY_CHECK, name="currency_supported"),
        CheckConstraint("due_date >= issue_date", name="due_after_issue"),
        CheckConstraint("tax_rate >= 0 AND tax_rate <= 100", name="tax_rate_range"),
        CheckConstraint("subtotal >= 0 AND tax_amount >= 0 AND total >= 0", name="amounts_non_negative"),
        CheckConstraint("total = subtotal + tax_amount", name="total_consistent"),
        CheckConstraint("(status = 'draft') = (number IS NULL)", name="number_when_issued"),
        CheckConstraint("(status = 'draft') = (sent_at IS NULL)", name="sent_at_when_issued"),
        CheckConstraint("(status = 'void') = (voided_at IS NOT NULL)", name="voided_at_when_void"),
        CheckConstraint("(status = 'paid') = (paid_at IS NOT NULL)", name="paid_at_when_paid"),
        CheckConstraint("version >= 1", name="version_positive"),
        Index("ix_invoices_user_status", "user_id", "status"),
        Index("ix_invoices_user_created", "user_id", text("created_at DESC"), text("id DESC")),
        Index("ix_invoices_client_id", "client_id"),
    )

    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    client_id: Mapped[uuid.UUID] = mapped_column(nullable=False)
    number: Mapped[str | None] = mapped_column(String(30))
    status: Mapped[InvoiceStatus] = mapped_column(_enum(InvoiceStatus, "invoice_status"), nullable=False)
    issue_date: Mapped[date] = mapped_column(Date, nullable=False)
    due_date: Mapped[date] = mapped_column(Date, nullable=False)
    currency: Mapped[str] = mapped_column(String(3), nullable=False)
    subtotal: Mapped[Decimal] = mapped_column(Numeric(14, 2), nullable=False, server_default=text("0"))
    tax_rate: Mapped[Decimal] = mapped_column(Numeric(5, 2), nullable=False, server_default=text("0"))
    tax_amount: Mapped[Decimal] = mapped_column(Numeric(14, 2), nullable=False, server_default=text("0"))
    total: Mapped[Decimal] = mapped_column(Numeric(14, 2), nullable=False, server_default=text("0"))
    notes: Mapped[str | None] = mapped_column(Text)
    # Snapshots taken on send, so an issued invoice never changes when the client or profile is edited later.
    bill_to_name: Mapped[str | None] = mapped_column(String(120))
    bill_to_company: Mapped[str | None] = mapped_column(String(160))
    bill_to_email: Mapped[str | None] = mapped_column(String(254))
    from_name: Mapped[str | None] = mapped_column(String(120))
    from_email: Mapped[str | None] = mapped_column(String(254))
    sent_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    paid_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    voided_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    version: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("1"))

    items: Mapped[list["InvoiceItem"]] = relationship(
        back_populates="invoice",
        cascade="all, delete-orphan",
        order_by="InvoiceItem.position",
        lazy="selectin",
    )
    payments: Mapped[list["Payment"]] = relationship(
        back_populates="invoice",
        order_by=lambda: (Payment.paid_on, Payment.created_at),
        lazy="selectin",
    )


class InvoiceItem(UUIDPrimaryKey, Base):
    __tablename__ = "invoice_items"
    __table_args__ = (
        CheckConstraint("amount >= 0", name="amount_non_negative"),
        CheckConstraint("quantity >= 0", name="quantity_non_negative"),
        CheckConstraint("unit_price >= 0", name="unit_price_non_negative"),
        CheckConstraint("kind = 'custom' OR duration_seconds IS NOT NULL", name="time_line_has_duration"),
        Index("ix_invoice_items_invoice", "invoice_id", "position"),
        Index("ix_invoice_items_time_entry_id", "time_entry_id"),
    )

    invoice_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("invoices.id", ondelete="CASCADE"), nullable=False)
    kind: Mapped[InvoiceItemKind] = mapped_column(_enum(InvoiceItemKind, "invoice_item_kind"), nullable=False)
    # Kept as an audit link; SET NULL so a released entry of a void invoice can still be deleted.
    time_entry_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("time_entries.id", ondelete="SET NULL"))
    description: Mapped[str] = mapped_column(String(500), nullable=False)
    service_date: Mapped[date | None] = mapped_column(Date)
    duration_seconds: Mapped[int | None] = mapped_column(Integer)
    quantity: Mapped[Decimal] = mapped_column(Numeric(12, 4), nullable=False)
    unit_price: Mapped[Decimal] = mapped_column(Numeric(10, 2), nullable=False)
    amount: Mapped[Decimal] = mapped_column(Numeric(14, 2), nullable=False)
    position: Mapped[int] = mapped_column(Integer, nullable=False)

    invoice: Mapped[Invoice] = relationship(back_populates="items")


class Payment(UUIDPrimaryKey, Base):
    __tablename__ = "payments"
    __table_args__ = (
        ForeignKeyConstraint(
            ["invoice_id", "user_id"],
            ["invoices.id", "invoices.user_id"],
            name="fk_payments_invoice_owner",
            ondelete="RESTRICT",
        ),
        CheckConstraint("amount > 0", name="amount_positive"),
        Index("ix_payments_user_paid_on", "user_id", "paid_on"),
        Index("ix_payments_invoice_id", "invoice_id"),
    )

    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    invoice_id: Mapped[uuid.UUID] = mapped_column(nullable=False)
    amount: Mapped[Decimal] = mapped_column(Numeric(14, 2), nullable=False)
    paid_on: Mapped[date] = mapped_column(Date, nullable=False)
    method: Mapped[PaymentMethod] = mapped_column(_enum(PaymentMethod, "payment_method"), nullable=False)
    note: Mapped[str | None] = mapped_column(String(500))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    invoice: Mapped[Invoice] = relationship(back_populates="payments")
