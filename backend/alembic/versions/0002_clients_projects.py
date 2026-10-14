"""Clients and projects with ownership-enforcing composite foreign keys.

Revision ID: 0002
Revises: 0001
Create Date: 2026-10-12
"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "0002"
down_revision: str | None = "0001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

CURRENCIES = "('USD', 'EUR', 'GBP', 'CAD', 'AUD', 'CHF', 'PLN', 'UAH')"

project_status = postgresql.ENUM("active", "on_hold", "completed", name="project_status", create_type=False)
billing_type = postgresql.ENUM("hourly", "fixed", "non_billable", name="billing_type", create_type=False)


def upgrade() -> None:
    project_status.create(op.get_bind(), checkfirst=True)
    billing_type.create(op.get_bind(), checkfirst=True)

    op.create_table(
        "clients",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("name", sa.String(120), nullable=False),
        sa.Column("email", sa.String(254)),
        sa.Column("company", sa.String(160)),
        sa.Column("notes", sa.Text()),
        sa.Column("default_hourly_rate", sa.Numeric(10, 2)),
        sa.Column("currency", sa.String(3), nullable=False),
        sa.Column("archived_at", sa.DateTime(timezone=True)),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.PrimaryKeyConstraint("id", name="pk_clients"),
        sa.UniqueConstraint("id", "user_id", name="uq_clients_id_user_id"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], name="fk_clients_user_id_users", ondelete="CASCADE"),
        sa.CheckConstraint(f"currency IN {CURRENCIES}", name="ck_clients_currency_supported"),
        sa.CheckConstraint(
            "default_hourly_rate IS NULL OR default_hourly_rate >= 0", name="ck_clients_default_rate_non_negative"
        ),
    )
    op.create_index("ix_clients_user_id", "clients", ["user_id"])
    op.create_index(
        "uq_clients_user_name_active",
        "clients",
        ["user_id", sa.text("lower(name)")],
        unique=True,
        postgresql_where=sa.text("archived_at IS NULL"),
    )

    op.create_table(
        "projects",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("client_id", sa.Uuid(), nullable=False),
        sa.Column("name", sa.String(120), nullable=False),
        sa.Column("description", sa.Text()),
        sa.Column("status", project_status, nullable=False, server_default="active"),
        sa.Column("billing_type", billing_type, nullable=False, server_default="hourly"),
        sa.Column("hourly_rate", sa.Numeric(10, 2)),
        sa.Column("fixed_fee", sa.Numeric(14, 2)),
        sa.Column("currency", sa.String(3), nullable=False),
        sa.Column("budget_hours", sa.Numeric(8, 2)),
        sa.Column("deadline", sa.Date()),
        sa.Column("color", sa.String(7), nullable=False, server_default="#8B7CFF"),
        sa.Column("archived_at", sa.DateTime(timezone=True)),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.PrimaryKeyConstraint("id", name="pk_projects"),
        sa.UniqueConstraint("id", "user_id", name="uq_projects_id_user_id"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], name="fk_projects_user_id_users", ondelete="CASCADE"),
        sa.ForeignKeyConstraint(
            ["client_id", "user_id"],
            ["clients.id", "clients.user_id"],
            name="fk_projects_client_owner",
            ondelete="RESTRICT",
        ),
        sa.CheckConstraint(f"currency IN {CURRENCIES}", name="ck_projects_currency_supported"),
        sa.CheckConstraint("hourly_rate IS NULL OR hourly_rate >= 0", name="ck_projects_hourly_rate_non_negative"),
        sa.CheckConstraint("fixed_fee IS NULL OR fixed_fee >= 0", name="ck_projects_fixed_fee_non_negative"),
        sa.CheckConstraint("billing_type <> 'fixed' OR fixed_fee IS NOT NULL", name="ck_projects_fixed_requires_fee"),
        sa.CheckConstraint("billing_type = 'hourly' OR hourly_rate IS NULL", name="ck_projects_rate_only_for_hourly"),
        sa.CheckConstraint("budget_hours IS NULL OR budget_hours > 0", name="ck_projects_budget_positive"),
        sa.CheckConstraint("color ~ '^#[0-9A-Fa-f]{6}$'", name="ck_projects_color_hex"),
    )
    op.create_index(
        "ix_projects_user_status", "projects", ["user_id", "status"], postgresql_where=sa.text("archived_at IS NULL")
    )
    op.create_index("ix_projects_client_id", "projects", ["client_id"])
    op.create_index(
        "uq_projects_client_name_active",
        "projects",
        ["client_id", sa.text("lower(name)")],
        unique=True,
        postgresql_where=sa.text("archived_at IS NULL"),
    )


def downgrade() -> None:
    op.drop_index("uq_projects_client_name_active", table_name="projects")
    op.drop_index("ix_projects_client_id", table_name="projects")
    op.drop_index("ix_projects_user_status", table_name="projects")
    op.drop_table("projects")
    op.drop_index("uq_clients_user_name_active", table_name="clients")
    op.drop_index("ix_clients_user_id", table_name="clients")
    op.drop_table("clients")
    billing_type.drop(op.get_bind(), checkfirst=True)
    project_status.drop(op.get_bind(), checkfirst=True)
