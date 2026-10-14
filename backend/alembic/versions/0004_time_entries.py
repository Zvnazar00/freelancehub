"""Time entries, pause intervals and idempotency keys.

Revision ID: 0004
Revises: 0003
Create Date: 2026-10-12
"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "0004"
down_revision: str | None = "0003"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

CURRENCIES = "('USD', 'EUR', 'GBP', 'CAD', 'AUD', 'CHF', 'PLN', 'UAH')"

entry_status = postgresql.ENUM("running", "paused", "stopped", name="time_entry_status", create_type=False)
entry_source = postgresql.ENUM("timer", "manual", name="entry_source", create_type=False)
rate_source = postgresql.ENUM("project", "client", "user", "none", name="rate_source", create_type=False)


def upgrade() -> None:
    bind = op.get_bind()
    for enum in (entry_status, entry_source, rate_source):
        enum.create(bind, checkfirst=True)

    op.create_table(
        "time_entries",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("project_id", sa.Uuid(), nullable=False),
        sa.Column("task_id", sa.Uuid()),
        sa.Column("description", sa.String(500), nullable=False, server_default=""),
        sa.Column("source", entry_source, nullable=False),
        sa.Column("status", entry_status, nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("ended_at", sa.DateTime(timezone=True)),
        sa.Column("duration_seconds", sa.Integer()),
        sa.Column("billable", sa.Boolean(), nullable=False),
        sa.Column("hourly_rate_snapshot", sa.Numeric(10, 2)),
        sa.Column("currency", sa.String(3), nullable=False),
        sa.Column("rate_source", rate_source, nullable=False),
        sa.Column("rate_corrected_at", sa.DateTime(timezone=True)),
        sa.Column("billable_amount", sa.Numeric(14, 2)),
        sa.Column("version", sa.Integer(), nullable=False, server_default=sa.text("1")),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.PrimaryKeyConstraint("id", name="pk_time_entries"),
        sa.UniqueConstraint("id", "user_id", name="uq_time_entries_id_user_id"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], name="fk_time_entries_user_id_users", ondelete="CASCADE"),
        sa.ForeignKeyConstraint(
            ["project_id", "user_id"],
            ["projects.id", "projects.user_id"],
            name="fk_time_entries_project_owner",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["task_id", "user_id"],
            ["tasks.id", "tasks.user_id"],
            name="fk_time_entries_task_owner",
            ondelete="SET NULL (task_id)",
        ),
        sa.CheckConstraint("(status = 'stopped') = (ended_at IS NOT NULL)", name="ck_time_entries_stopped_has_end"),
        sa.CheckConstraint("ended_at IS NULL OR ended_at > started_at", name="ck_time_entries_end_after_start"),
        sa.CheckConstraint(
            "(status = 'stopped') = (duration_seconds IS NOT NULL)", name="ck_time_entries_duration_when_stopped"
        ),
        sa.CheckConstraint(
            "duration_seconds IS NULL OR duration_seconds >= 0", name="ck_time_entries_duration_non_negative"
        ),
        sa.CheckConstraint("source = 'timer' OR status = 'stopped'", name="ck_time_entries_manual_is_stopped"),
        sa.CheckConstraint(
            "source = 'timer' OR ended_at - started_at <= interval '24 hours'", name="ck_time_entries_manual_max_24h"
        ),
        sa.CheckConstraint(
            "billable_amount IS NULL OR billable_amount >= 0", name="ck_time_entries_amount_non_negative"
        ),
        sa.CheckConstraint(
            "hourly_rate_snapshot IS NULL OR hourly_rate_snapshot >= 0", name="ck_time_entries_rate_non_negative"
        ),
        sa.CheckConstraint(f"currency IN {CURRENCIES}", name="ck_time_entries_currency_supported"),
        sa.CheckConstraint("version >= 1", name="ck_time_entries_version_positive"),
        postgresql.ExcludeConstraint(
            ("user_id", "="),
            (sa.text("tstzrange(started_at, ended_at, '[)')"), "&&"),
            name="ex_time_entries_no_overlap",
            using="gist",
        ),
    )
    op.create_index(
        "ux_time_entries_one_active",
        "time_entries",
        ["user_id"],
        unique=True,
        postgresql_where=sa.text("status IN ('running', 'paused')"),
    )
    op.create_index(
        "ix_time_entries_user_started", "time_entries", ["user_id", sa.text("started_at DESC"), sa.text("id DESC")]
    )
    op.create_index("ix_time_entries_project_started", "time_entries", ["project_id", "started_at"])

    op.create_table(
        "time_entry_pauses",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("time_entry_id", sa.Uuid(), nullable=False),
        sa.Column("paused_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("resumed_at", sa.DateTime(timezone=True)),
        sa.PrimaryKeyConstraint("id", name="pk_time_entry_pauses"),
        sa.ForeignKeyConstraint(
            ["time_entry_id"],
            ["time_entries.id"],
            name="fk_time_entry_pauses_time_entry_id_time_entries",
            ondelete="CASCADE",
        ),
        sa.CheckConstraint(
            "resumed_at IS NULL OR resumed_at >= paused_at", name="ck_time_entry_pauses_resume_after_pause"
        ),
    )
    op.create_index(
        "ux_pauses_one_open",
        "time_entry_pauses",
        ["time_entry_id"],
        unique=True,
        postgresql_where=sa.text("resumed_at IS NULL"),
    )
    op.create_index("ix_pauses_entry", "time_entry_pauses", ["time_entry_id", "paused_at"])

    op.create_table(
        "idempotency_keys",
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("key", sa.String(100), nullable=False),
        sa.Column("endpoint", sa.String(100), nullable=False),
        sa.Column("request_hash", sa.String(64), nullable=False),
        sa.Column("status_code", sa.SmallInteger(), nullable=False),
        sa.Column("response_body", sa.Text(), nullable=False),  # exact bytes; JSONB would reorder keys
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.PrimaryKeyConstraint("user_id", "key", name="pk_idempotency_keys"),
        sa.ForeignKeyConstraint(
            ["user_id"], ["users.id"], name="fk_idempotency_keys_user_id_users", ondelete="CASCADE"
        ),
    )
    op.create_index("ix_idempotency_keys_created_at", "idempotency_keys", ["created_at"])


def downgrade() -> None:
    op.drop_index("ix_idempotency_keys_created_at", table_name="idempotency_keys")
    op.drop_table("idempotency_keys")
    op.drop_index("ix_pauses_entry", table_name="time_entry_pauses")
    op.drop_index("ux_pauses_one_open", table_name="time_entry_pauses")
    op.drop_table("time_entry_pauses")
    op.drop_index("ix_time_entries_project_started", table_name="time_entries")
    op.drop_index("ix_time_entries_user_started", table_name="time_entries")
    op.drop_index("ux_time_entries_one_active", table_name="time_entries")
    op.drop_table("time_entries")
    bind = op.get_bind()
    for enum in (rate_source, entry_source, entry_status):
        enum.drop(bind, checkfirst=True)
