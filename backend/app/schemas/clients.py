import uuid
from datetime import datetime
from typing import Annotated

from pydantic import EmailStr, Field, StringConstraints, model_validator

from app.schemas.common import Currency, CurrencyAmount, Rate, ResponseModel, StrictModel, Timestamped

Name = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=120)]
Company = Annotated[str, StringConstraints(strip_whitespace=True, max_length=160)]
Notes = Annotated[str, StringConstraints(max_length=5000)]


class ClientCreate(StrictModel):
    name: Name
    email: EmailStr | None = None
    company: Company | None = None
    notes: Notes | None = None
    default_hourly_rate: Rate | None = None
    currency: Currency | None = None  # defaults to the user's default currency


class ClientUpdate(StrictModel):
    name: Name | None = None
    email: EmailStr | None = None
    company: Company | None = None
    notes: Notes | None = None
    default_hourly_rate: Rate | None = None
    currency: Currency | None = None

    @model_validator(mode="after")
    def _non_nullable(self) -> "ClientUpdate":
        for field in ("name", "currency"):
            if field in self.model_fields_set and getattr(self, field) is None:
                raise ValueError(f"{field} cannot be null")
        return self


class ClientStats(ResponseModel):
    active_projects: int
    tracked_seconds: int = Field(description="Net seconds of stopped entries across the client's projects")
    unbilled: list[CurrencyAmount] = Field(
        description="Billable amount of stopped entries that are not on a sent/paid invoice, per currency"
    )


class ClientOut(Timestamped):
    id: uuid.UUID
    name: str
    email: str | None
    company: str | None
    notes: str | None
    default_hourly_rate: Rate | None
    currency: str
    archived_at: datetime | None
    stats: ClientStats
