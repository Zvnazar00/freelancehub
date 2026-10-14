"""Invoices, invoice items, payments, and the time_entries → invoice link.

Revision ID: 0005
Revises: 0004
Create Date: 2026-10-12
"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "0005"
down_revision: str | None = "0004"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

CURRENCIES = "('USD', 'EUR', 'GBP', 'CAD', 'AUD', 'CHF', 'PLN', 'UAH')"

invoice_status = postgresql.ENUM("draft", "sent", "paid", "void", name="invoice_status", create_type=False)
item_kind = postgresql.ENUM("time", "custom", name="invoice_item_kind", create_type=False)
payment_method = postgresql.ENUM(
    "bank_transfer", "card", "cash", "paypal", "other", name="payment_method", create_type=False
)


def upgrade() -> None:
    bind = op.get_bind()
    for enum in (invoice_status, item_kind, payment_method):
        enum.create(bind, checkfirst=True)

    op.create_table(
        "invoices",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("client_id", sa.Uuid(), nullable=False),
        sa.Column("number", sa.String(30)),
        sa.Column("status", invoice_status, nullable=False),
        sa.Column("issue_date", sa.Date(), nullable=False),
        sa.Column("due_date", sa.Date(), nullable=False),
        sa.Column("currency", sa.String(3), nullable=False),
        sa.Column("subtotal", sa.Numeric(14, 2), nullable=False, server_default=sa.text("0")),
        sa.Column("tax_rate", sa.Numeric(5, 2), nullable=False, server_default=sa.text("0")),
        sa.Column("tax_amount", sa.Numeric(14, 2), nullable=False, server_default=sa.text("0")),
        sa.Column("total", sa.Numeric(14, 2), nullable=False, server_default=sa.text("0")),
        sa.Column("notes", sa.Text()),
        sa.Column("bill_to_name", sa.String(120)),
        sa.Column("bill_to_company", sa.String(160)),
        sa.Column("bill_to_email", sa.String(254)),
        sa.Column("from_name", sa.String(120)),
        sa.Column("from_email", sa.String(254)),
        sa.Column("sent_at", sa.DateTime(timezone=True)),
        sa.Column("paid_at", sa.DateTime(timezone=True)),
        sa.Column("voided_at", sa.DateTime(timezone=True)),
        sa.Column("version", sa.Integer(), nullable=False, server_default=sa.text("1")),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.PrimaryKeyConstraint("id", name="pk_invoices"),
        sa.UniqueConstraint("id", "user_id", name="uq_invoices_id_user_id"),
        sa.UniqueConstraint("user_id", "number", name="uq_invoices_user_number"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], name="fk_invoices_user_id_users", ondelete="CASCADE"),
        sa.ForeignKeyConstraint(
            ["client_id", "user_id"],
            ["clients.id", "clients.user_id"],
            name="fk_invoices_client_owner",
            ondelete="RESTRICT",
        ),
        sa.CheckConstraint(f"currency IN {CURRENCIES}", name="ck_invoices_currency_supported"),
        sa.CheckConstraint("due_date >= issue_date", name="ck_invoices_due_after_issue"),
        sa.CheckConstraint("tax_rate >= 0 AND tax_rate <= 100", name="ck_invoices_tax_rate_range"),
        sa.CheckConstraint("subtotal >= 0 AND tax_amount >= 0 AND total >= 0", name="ck_invoices_amounts_non_negative"),
        sa.CheckConstraint("total = subtotal + tax_amount", name="ck_invoices_total_consistent"),
        sa.CheckConstraint("(status = 'draft') = (number IS NULL)", name="ck_invoices_number_when_issued"),
        sa.CheckConstraint("(status = 'draft') = (sent_at IS NULL)", name="ck_invoices_sent_at_when_issued"),
        sa.CheckConstraint("(status = 'void') = (voided_at IS NOT NULL)", name="ck_invoices_voided_at_when_void"),
        sa.CheckConstraint("(status = 'paid') = (paid_at IS NOT NULL)", name="ck_invoices_paid_at_when_paid"),
        sa.CheckConstraint("version >= 1", name="ck_invoices_version_positive"),
    )
    op.create_index("ix_invoices_user_status", "invoices", ["user_id", "status"])
    op.create_index("ix_invoices_user_created", "invoices", ["user_id", sa.text("created_at DESC"), sa.text("id DESC")])
    op.create_index("ix_invoices_client_id", "invoices", ["client_id"])

    op.create_table(
        "invoice_items",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("invoice_id", sa.Uuid(), nullable=False),
        sa.Column("kind", item_kind, nullable=False),
        sa.Column("time_entry_id", sa.Uuid()),
        sa.Column("description", sa.String(500), nullable=False),
        sa.Column("service_date", sa.Date()),
        sa.Column("duration_seconds", sa.Integer()),
        sa.Column("quantity", sa.Numeric(12, 4), nullable=False),
        sa.Column("unit_price", sa.Numeric(10, 2), nullable=False),
        sa.Column("amount", sa.Numeric(14, 2), nullable=False),
        sa.Column("position", sa.Integer(), nullable=False),
        sa.PrimaryKeyConstraint("id", name="pk_invoice_items"),
        sa.ForeignKeyConstraint(
            ["invoice_id"], ["invoices.id"], name="fk_invoice_items_invoice_id_invoices", ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["time_entry_id"],
            ["time_entries.id"],
            name="fk_invoice_items_time_entry_id_time_entries",
            ondelete="SET NULL",
        ),
        sa.CheckConstraint("amount >= 0", name="ck_invoice_items_amount_non_negative"),
        sa.CheckConstraint("quantity >= 0", name="ck_invoice_items_quantity_non_negative"),
        sa.CheckConstraint("unit_price >= 0", name="ck_invoice_items_unit_price_non_negative"),
        sa.CheckConstraint(
            "kind = 'custom' OR duration_seconds IS NOT NULL", name="ck_invoice_items_time_line_has_duration"
        ),
    )
    op.create_index("ix_invoice_items_invoice", "invoice_items", ["invoice_id", "position"])
    op.create_index("ix_invoice_items_time_entry_id", "invoice_items", ["time_entry_id"])

    op.create_table(
        "payments",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("invoice_id", sa.Uuid(), nullable=False),
        sa.Column("amount", sa.Numeric(14, 2), nullable=False),
        sa.Column("paid_on", sa.Date(), nullable=False),
        sa.Column("method", payment_method, nullable=False),
        sa.Column("note", sa.String(500)),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.PrimaryKeyConstraint("id", name="pk_payments"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], name="fk_payments_user_id_users", ondelete="CASCADE"),
        sa.ForeignKeyConstraint(
            ["invoice_id", "user_id"],
            ["invoices.id", "invoices.user_id"],
            name="fk_payments_invoice_owner",
            ondelete="RESTRICT",
        ),
        sa.CheckConstraint("amount > 0", name="ck_payments_amount_positive"),
    )
    op.create_index("ix_payments_user_paid_on", "payments", ["user_id", "paid_on"])
    op.create_index("ix_payments_invoice_id", "payments", ["invoice_id"])

    op.add_column("time_entries", sa.Column("invoice_id", sa.Uuid()))
    op.create_foreign_key(
        "fk_time_entries_invoice_owner",
        "time_entries",
        "invoices",
        ["invoice_id", "user_id"],
        ["id", "user_id"],
        ondelete="SET NULL (invoice_id)",
    )
    op.create_check_constraint(
        "ck_time_entries_invoiced_is_stopped", "time_entries", "invoice_id IS NULL OR status = 'stopped'"
    )
    op.create_index("ix_time_entries_invoice_id", "time_entries", ["invoice_id"])


def downgrade() -> None:
    op.drop_index("ix_time_entries_invoice_id", table_name="time_entries")
    op.drop_constraint("ck_time_entries_invoiced_is_stopped", "time_entries", type_="check")
    op.drop_constraint("fk_time_entries_invoice_owner", "time_entries", type_="foreignkey")
    op.drop_column("time_entries", "invoice_id")
    op.drop_index("ix_payments_invoice_id", table_name="payments")
    op.drop_index("ix_payments_user_paid_on", table_name="payments")
    op.drop_table("payments")
    op.drop_index("ix_invoice_items_time_entry_id", table_name="invoice_items")
    op.drop_index("ix_invoice_items_invoice", table_name="invoice_items")
    op.drop_table("invoice_items")
    op.drop_index("ix_invoices_client_id", table_name="invoices")
    op.drop_index("ix_invoices_user_created", table_name="invoices")
    op.drop_index("ix_invoices_user_status", table_name="invoices")
    op.drop_table("invoices")
    bind = op.get_bind()
    for enum in (payment_method, item_kind, invoice_status):
        enum.drop(bind, checkfirst=True)
