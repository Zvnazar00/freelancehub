import uuid
from datetime import date, datetime
from typing import Annotated

from pydantic import Field, StringConstraints, model_validator

from app.models.enums import BillingType, ProjectStatus
from app.schemas.common import (
    Amount,
    Currency,
    CurrencyAmount,
    HexColor,
    Hours,
    Rate,
    ResponseModel,
    StrictModel,
    Timestamped,
)

Name = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=120)]
Description = Annotated[str, StringConstraints(max_length=5000)]


class ProjectCreate(StrictModel):
    client_id: uuid.UUID
    name: Name
    description: Description | None = None
    status: ProjectStatus = ProjectStatus.active
    billing_type: BillingType = BillingType.hourly
    hourly_rate: Rate | None = None
    fixed_fee: Amount | None = None
    currency: Currency | None = None  # defaults to the client's currency
    budget_hours: Hours | None = None
    deadline: date | None = None
    color: HexColor = "#8B7CFF"


class ProjectUpdate(StrictModel):
    client_id: uuid.UUID | None = None
    name: Name | None = None
    description: Description | None = None
    status: ProjectStatus | None = None
    billing_type: BillingType | None = None
    hourly_rate: Rate | None = None
    fixed_fee: Amount | None = None
    currency: Currency | None = None
    budget_hours: Hours | None = None
    deadline: date | None = None
    color: HexColor | None = None

    @model_validator(mode="after")
    def _non_nullable(self) -> "ProjectUpdate":
        for field in ("client_id", "name", "status", "billing_type", "currency", "color"):
            if field in self.model_fields_set and getattr(self, field) is None:
                raise ValueError(f"{field} cannot be null")
        return self


class ClientRef(ResponseModel):
    id: uuid.UUID
    name: str


class ProjectStats(ResponseModel):
    tasks_total: int
    tasks_done: int
    tracked_seconds: int = Field(description="Net seconds of stopped entries (active timer excluded)")
    unbilled: list[CurrencyAmount] = Field(
        description="Billable amount of stopped entries that are not on a sent/paid invoice, per currency"
    )


class ProjectOut(Timestamped):
    id: uuid.UUID
    client: ClientRef
    name: str
    description: str | None
    status: ProjectStatus
    billing_type: BillingType
    hourly_rate: Rate | None
    fixed_fee: Amount | None
    currency: str
    budget_hours: Hours | None
    deadline: date | None
    color: str
    archived_at: datetime | None
    stats: ProjectStats
