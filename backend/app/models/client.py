import uuid
from datetime import datetime
from decimal import Decimal

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Index, Numeric, String, Text, UniqueConstraint, func, text
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, Timestamps, UUIDPrimaryKey
from app.models.user import CURRENCY_CHECK


class Client(UUIDPrimaryKey, Timestamps, Base):
    __tablename__ = "clients"
    __table_args__ = (
        UniqueConstraint("id", "user_id", name="uq_clients_id_user_id"),
        CheckConstraint(CURRENCY_CHECK, name="currency_supported"),
        CheckConstraint("default_hourly_rate IS NULL OR default_hourly_rate >= 0", name="default_rate_non_negative"),
        Index("ix_clients_user_id", "user_id"),
        Index(
            "uq_clients_user_name_active",
            "user_id",
            func.lower(text("name")),
            unique=True,
            postgresql_where=text("archived_at IS NULL"),
        ),
    )

    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    email: Mapped[str | None] = mapped_column(String(254))
    company: Mapped[str | None] = mapped_column(String(160))
    notes: Mapped[str | None] = mapped_column(Text)
    default_hourly_rate: Mapped[Decimal | None] = mapped_column(Numeric(10, 2))
    currency: Mapped[str] = mapped_column(String(3), nullable=False)
    archived_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
