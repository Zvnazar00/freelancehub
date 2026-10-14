import uuid
from datetime import date, datetime
from typing import Literal

from pydantic import Field

from app.models.enums import BillingType
from app.schemas.common import Amount, CurrencyAmount, Rate, ResponseModel

Period = Literal["today", "week", "month", "quarter", "year"]
Interval = Literal["day", "week", "month"]
GroupBy = Literal["project", "client"]


class DateRange(ResponseModel):
    from_: date = Field(serialization_alias="from")
    to: date


class MoneyFlow(ResponseModel):
    """What happened inside the period, per currency. Never added across currencies."""

    currency: str
    tracked: Amount = Field(description="Value of billable time tracked in the period (not money received)")
    previous_tracked: Amount = Field(description="Same, for the previous period of equal length")
    invoiced: Amount = Field(description="Totals of invoices issued in the period (sent or paid, void excluded)")
    received: Amount = Field(description="Payments recorded with a payment date in the period")
    billable_seconds: int
    effective_hourly_rate: Rate | None = Field(description="tracked / billable hours, half-up to 2 dp")


class Balance(ResponseModel):
    """Balances as of now (not limited to the period), per currency."""

    currency: str
    unbilled: Amount = Field(description="Billable tracked value not yet on a sent invoice")
    outstanding: Amount = Field(description="Sent invoices minus payments received")
    overdue: Amount = Field(description="Part of outstanding whose due date has passed (user time zone)")


class InvoiceCounts(ResponseModel):
    draft: int
    open: int
    overdue: int


class ProjectSlice(ResponseModel):
    id: uuid.UUID
    name: str
    color: str
    client_name: str
    seconds: int
    amounts: list[CurrencyAmount]


class DashboardSummary(ResponseModel):
    range: DateRange
    previous_range: DateRange
    tracked_seconds: int = Field(description="Stopped entries started in the period (user time zone)")
    billable_seconds: int
    previous_tracked_seconds: int
    entries: int
    flows: list[MoneyFlow]
    balances: list[Balance]
    invoices: InvoiceCounts
    top_projects: list[ProjectSlice]
    server_time: datetime


class SeriesPoint(ResponseModel):
    start: date
    end: date = Field(description="Inclusive last local date of the bucket")
    seconds: int
    billable_seconds: int
    tracked: list[CurrencyAmount]
    received: list[CurrencyAmount]


class Timeseries(ResponseModel):
    range: DateRange
    interval: Interval
    points: list[SeriesPoint]


class CurrencyRate(ResponseModel):
    currency: str
    rate: Rate


class BreakdownRow(ResponseModel):
    id: uuid.UUID
    name: str
    color: str | None
    client_name: str | None
    billing_type: BillingType | None
    seconds: int
    billable_seconds: int
    share: float = Field(description="Share of the period's tracked seconds (0-1), for display only")
    amounts: list[CurrencyAmount]
    effective_hourly_rate: list[CurrencyRate] = Field(
        description="Hourly: amount / priced hours in the period. Fixed fee: fee / all tracked hours of the project"
    )


class Breakdown(ResponseModel):
    range: DateRange
    group_by: GroupBy
    total_seconds: int
    rows: list[BreakdownRow]


class TaskSlice(ResponseModel):
    task_id: uuid.UUID | None
    title: str | None
    seconds: int
    amounts: list[CurrencyAmount]


class ProjectMoney(ResponseModel):
    currency: str
    tracked: Amount = Field(description="All billable tracked value")
    unbilled: Amount
    invoiced: Amount = Field(description="Entries of this project on sent or paid invoices")


class ResolvedRateOut(ResponseModel):
    rate: Rate | None
    currency: str
    source: str = Field(description="project | client | user | none — what a new entry would snapshot")


class ProjectSummary(ResponseModel):
    project_id: uuid.UUID
    billing_type: BillingType
    currency: str
    tracked_seconds: int
    billable_seconds: int
    entries: int
    first_entry_at: datetime | None
    last_entry_at: datetime | None
    budget_hours: Amount | None
    budget_used: float | None = Field(description="tracked hours / budget hours (may exceed 1); display only")
    fixed_fee: Amount | None
    current_rate: ResolvedRateOut
    effective_hourly_rate: list[CurrencyRate]
    money: list[ProjectMoney]
    by_task: list[TaskSlice]
    last_30_days_seconds: int
