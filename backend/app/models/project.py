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
    Numeric,
    String,
    Text,
    UniqueConstraint,
    func,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, Timestamps, UUIDPrimaryKey
from app.models.enums import BillingType, ProjectStatus
from app.models.user import CURRENCY_CHECK


class Project(UUIDPrimaryKey, Timestamps, Base):
    __tablename__ = "projects"
    __table_args__ = (
        UniqueConstraint("id", "user_id", name="uq_projects_id_user_id"),
        # Composite FK: a project can only reference a client of the same user (enforced by the DB).
        ForeignKeyConstraint(
            ["client_id", "user_id"],
            ["clients.id", "clients.user_id"],
            name="fk_projects_client_owner",
            ondelete="RESTRICT",
        ),
        CheckConstraint(CURRENCY_CHECK, name="currency_supported"),
        CheckConstraint("hourly_rate IS NULL OR hourly_rate >= 0", name="hourly_rate_non_negative"),
        CheckConstraint("fixed_fee IS NULL OR fixed_fee >= 0", name="fixed_fee_non_negative"),
        CheckConstraint("billing_type <> 'fixed' OR fixed_fee IS NOT NULL", name="fixed_requires_fee"),
        CheckConstraint("billing_type = 'hourly' OR hourly_rate IS NULL", name="rate_only_for_hourly"),
        CheckConstraint("budget_hours IS NULL OR budget_hours > 0", name="budget_positive"),
        CheckConstraint("color ~ '^#[0-9A-Fa-f]{6}$'", name="color_hex"),
        Index("ix_projects_user_status", "user_id", "status", postgresql_where=text("archived_at IS NULL")),
        Index("ix_projects_client_id", "client_id"),
        Index(
            "uq_projects_client_name_active",
            "client_id",
            func.lower(text("name")),
            unique=True,
            postgresql_where=text("archived_at IS NULL"),
        ),
    )

    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    client_id: Mapped[uuid.UUID] = mapped_column(nullable=False)
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    status: Mapped[ProjectStatus] = mapped_column(
        Enum(ProjectStatus, name="project_status", values_callable=lambda e: [m.value for m in e]),
        nullable=False,
        server_default=ProjectStatus.active.value,
    )
    billing_type: Mapped[BillingType] = mapped_column(
        Enum(BillingType, name="billing_type", values_callable=lambda e: [m.value for m in e]),
        nullable=False,
        server_default=BillingType.hourly.value,
    )
    hourly_rate: Mapped[Decimal | None] = mapped_column(Numeric(10, 2))
    fixed_fee: Mapped[Decimal | None] = mapped_column(Numeric(14, 2))
    currency: Mapped[str] = mapped_column(String(3), nullable=False)
    budget_hours: Mapped[Decimal | None] = mapped_column(Numeric(8, 2))
    deadline: Mapped[date | None] = mapped_column(Date)
    color: Mapped[str] = mapped_column(String(7), nullable=False, server_default="#8B7CFF")
    archived_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
