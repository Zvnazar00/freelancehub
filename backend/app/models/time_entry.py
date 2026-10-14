"""Time entries, their pause intervals, and idempotency records (docs/database.md §3.6-3.8)."""

import uuid
from datetime import datetime
from decimal import Decimal

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    Enum,
    ForeignKey,
    ForeignKeyConstraint,
    Index,
    Integer,
    Numeric,
    PrimaryKeyConstraint,
    SmallInteger,
    String,
    Text,
    UniqueConstraint,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import ExcludeConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, Timestamps, UUIDPrimaryKey
from app.models.enums import EntrySource, RateSource, TimeEntryStatus
from app.models.user import CURRENCY_CHECK


def _enum(cls: type, name: str) -> Enum:
    return Enum(cls, name=name, values_callable=lambda e: [m.value for m in e])


ACTIVE_STATUSES = (TimeEntryStatus.running, TimeEntryStatus.paused)


class TimeEntry(UUIDPrimaryKey, Timestamps, Base):
    __tablename__ = "time_entries"
    __table_args__ = (
        UniqueConstraint("id", "user_id", name="uq_time_entries_id_user_id"),
        ForeignKeyConstraint(
            ["project_id", "user_id"],
            ["projects.id", "projects.user_id"],
            name="fk_time_entries_project_owner",
            ondelete="RESTRICT",
        ),
        # Deleting a task keeps the entry and only clears task_id (PostgreSQL 15+ column-list SET NULL).
        ForeignKeyConstraint(
            ["task_id", "user_id"],
            ["tasks.id", "tasks.user_id"],
            name="fk_time_entries_task_owner",
            ondelete="SET NULL (task_id)",
        ),
        # An entry on an invoice is locked; deleting a draft invoice releases it (SET NULL of invoice_id only).
        ForeignKeyConstraint(
            ["invoice_id", "user_id"],
            ["invoices.id", "invoices.user_id"],
            name="fk_time_entries_invoice_owner",
            ondelete="SET NULL (invoice_id)",
        ),
        CheckConstraint("invoice_id IS NULL OR status = 'stopped'", name="invoiced_is_stopped"),
        CheckConstraint("(status = 'stopped') = (ended_at IS NOT NULL)", name="stopped_has_end"),
        CheckConstraint("ended_at IS NULL OR ended_at > started_at", name="end_after_start"),
        CheckConstraint("(status = 'stopped') = (duration_seconds IS NOT NULL)", name="duration_when_stopped"),
        CheckConstraint("duration_seconds IS NULL OR duration_seconds >= 0", name="duration_non_negative"),
        CheckConstraint("source = 'timer' OR status = 'stopped'", name="manual_is_stopped"),
        CheckConstraint("source = 'timer' OR ended_at - started_at <= interval '24 hours'", name="manual_max_24h"),
        CheckConstraint("billable_amount IS NULL OR billable_amount >= 0", name="amount_non_negative"),
        CheckConstraint("hourly_rate_snapshot IS NULL OR hourly_rate_snapshot >= 0", name="rate_non_negative"),
        CheckConstraint(CURRENCY_CHECK, name="currency_supported"),
        CheckConstraint("version >= 1", name="version_positive"),
        # Invariant: at most one running/paused entry per user.
        Index(
            "ux_time_entries_one_active",
            "user_id",
            unique=True,
            postgresql_where=text("status IN ('running', 'paused')"),
        ),
        # Invariant: a user's entries never overlap (an active entry is open-ended).
        ExcludeConstraint(
            ("user_id", "="),
            (text("tstzrange(started_at, ended_at, '[)')"), "&&"),
            name="ex_time_entries_no_overlap",
            using="gist",
        ),
        Index("ix_time_entries_user_started", "user_id", text("started_at DESC"), text("id DESC")),
        Index("ix_time_entries_project_started", "project_id", "started_at"),
        Index("ix_time_entries_invoice_id", "invoice_id"),
    )

    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    project_id: Mapped[uuid.UUID] = mapped_column(nullable=False)
    task_id: Mapped[uuid.UUID | None] = mapped_column()
    description: Mapped[str] = mapped_column(String(500), nullable=False, server_default="")
    source: Mapped[EntrySource] = mapped_column(_enum(EntrySource, "entry_source"), nullable=False)
    status: Mapped[TimeEntryStatus] = mapped_column(_enum(TimeEntryStatus, "time_entry_status"), nullable=False)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    ended_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    duration_seconds: Mapped[int | None] = mapped_column(Integer)
    billable: Mapped[bool] = mapped_column(Boolean, nullable=False)
    hourly_rate_snapshot: Mapped[Decimal | None] = mapped_column(Numeric(10, 2))
    currency: Mapped[str] = mapped_column(String(3), nullable=False)
    rate_source: Mapped[RateSource] = mapped_column(_enum(RateSource, "rate_source"), nullable=False)
    rate_corrected_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    billable_amount: Mapped[Decimal | None] = mapped_column(Numeric(14, 2))
    invoice_id: Mapped[uuid.UUID | None] = mapped_column()
    version: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("1"))

    pauses: Mapped[list["TimeEntryPause"]] = relationship(
        back_populates="entry",
        cascade="all, delete-orphan",
        order_by="TimeEntryPause.paused_at",
        lazy="selectin",
    )

    @property
    def is_active(self) -> bool:
        return self.status in ACTIVE_STATUSES


class TimeEntryPause(UUIDPrimaryKey, Base):
    __tablename__ = "time_entry_pauses"
    __table_args__ = (
        CheckConstraint("resumed_at IS NULL OR resumed_at >= paused_at", name="resume_after_pause"),
        # Invariant: at most one open pause per entry.
        Index("ux_pauses_one_open", "time_entry_id", unique=True, postgresql_where=text("resumed_at IS NULL")),
        Index("ix_pauses_entry", "time_entry_id", "paused_at"),
    )

    time_entry_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("time_entries.id", ondelete="CASCADE"), nullable=False)
    paused_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    resumed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    entry: Mapped[TimeEntry] = relationship(back_populates="pauses")


class IdempotencyKey(Base):
    __tablename__ = "idempotency_keys"
    __table_args__ = (
        PrimaryKeyConstraint("user_id", "key", name="pk_idempotency_keys"),
        Index("ix_idempotency_keys_created_at", "created_at"),
    )

    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    key: Mapped[str] = mapped_column(String(100), nullable=False)
    endpoint: Mapped[str] = mapped_column(String(100), nullable=False)
    request_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    status_code: Mapped[int] = mapped_column(SmallInteger, nullable=False)
    # Exact response bytes (TEXT, not JSONB: JSONB reorders keys, and replays must be byte-identical).
    response_body: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
