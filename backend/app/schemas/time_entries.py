import uuid
from datetime import date, datetime
from typing import Annotated

from pydantic import AwareDatetime, Field, StringConstraints, model_validator

from app.models.enums import EntrySource, RateSource, TimeEntryStatus
from app.schemas.common import Amount, Rate, ResponseModel, StrictModel

Description = Annotated[str, StringConstraints(strip_whitespace=True, max_length=500)]


# ---------- requests ----------


class TimerStart(StrictModel):
    id: uuid.UUID = Field(description="Client-generated entry ID; repeating a start with the same ID is idempotent")
    project_id: uuid.UUID
    task_id: uuid.UUID | None = None
    description: Description = ""
    billable: bool | None = None
    at: AwareDatetime | None = Field(default=None, description="Only for commands queued offline; validated")


class TimerCommand(StrictModel):
    at: AwareDatetime | None = None


class TimerStop(TimerCommand):
    description: Description | None = None


class ActiveEntryUpdate(StrictModel):
    description: Description | None = None
    task_id: uuid.UUID | None = None
    billable: bool | None = None
    started_at: AwareDatetime | None = None

    @model_validator(mode="after")
    def _non_nullable(self) -> "ActiveEntryUpdate":
        for field in ("description", "billable", "started_at"):
            if field in self.model_fields_set and getattr(self, field) is None:
                raise ValueError(f"{field} cannot be null")
        return self


class ManualEntryCreate(StrictModel):
    project_id: uuid.UUID
    task_id: uuid.UUID | None = None
    description: Description = ""
    started_at: AwareDatetime
    ended_at: AwareDatetime
    billable: bool | None = None

    @model_validator(mode="after")
    def _order(self) -> "ManualEntryCreate":
        if self.ended_at <= self.started_at:
            raise ValueError("ended_at must be after started_at")
        return self


class EntryUpdate(StrictModel):
    version: int = Field(ge=1, description="Current version for optimistic locking")
    description: Description | None = None
    project_id: uuid.UUID | None = None
    task_id: uuid.UUID | None = None
    started_at: AwareDatetime | None = None
    ended_at: AwareDatetime | None = None
    billable: bool | None = None
    reprice: bool = Field(default=False, description="Explicit correction: re-resolve the hourly rate snapshot")

    @model_validator(mode="after")
    def _non_nullable(self) -> "EntryUpdate":
        for field in ("description", "project_id", "started_at", "ended_at", "billable"):
            if field in self.model_fields_set and getattr(self, field) is None:
                raise ValueError(f"{field} cannot be null")
        return self


# ---------- responses ----------


class PauseOut(ResponseModel):
    paused_at: datetime
    resumed_at: datetime | None


class ProjectRef(ResponseModel):
    id: uuid.UUID
    name: str
    color: str


class TaskRef(ResponseModel):
    id: uuid.UUID
    title: str


class TimeEntryOut(ResponseModel):
    id: uuid.UUID
    project: ProjectRef
    task: TaskRef | None
    description: str
    source: EntrySource
    status: TimeEntryStatus
    started_at: datetime
    ended_at: datetime | None
    pauses: list[PauseOut]
    duration_seconds: int | None = Field(description="Net of pauses; set once stopped")
    elapsed_seconds: int = Field(description="Net seconds as of server_time (equals duration once stopped)")
    billable: bool
    hourly_rate: Rate | None = Field(description="Rate snapshot taken when the entry was created")
    currency: str
    rate_source: RateSource
    rate_corrected_at: datetime | None
    billable_amount: Amount | None
    invoice_id: uuid.UUID | None = Field(description="Set while the entry is on an invoice (draft included); locked")
    version: int
    created_at: datetime
    updated_at: datetime


class TimerState(ResponseModel):
    entry: TimeEntryOut | None
    server_time: datetime


class CurrencySummary(ResponseModel):
    currency: str
    seconds: int
    billable_seconds: int
    amount: Amount


class DayTotal(ResponseModel):
    date: date
    seconds: int
    entries: int


class EntryPage(ResponseModel):
    items: list[TimeEntryOut]
    next_cursor: str | None
    summary: list[CurrencySummary] = Field(description="Stopped entries in the whole filter range, per currency")
    days: list[DayTotal] = Field(description="Stopped entries per local day (user time zone, by start)")
    server_time: datetime
