"""Dashboard, analytics and project summaries (docs/architecture.md §8).

Vocabulary is strict and mirrored in the UI:
  tracked     — value of billable work tracked in a period (sum of per-entry rounded amounts);
  invoiced    — totals of invoices issued (sent or paid) in a period;
  received    — payments recorded in a period;
  unbilled / outstanding / overdue — balances as of now.
Nothing is ever added across currencies. Ranges are local calendar dates in the user's time zone,
entries are attributed to the local date of `started_at` (assumption A-8).
"""

import uuid
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from decimal import Decimal

from sqlalchemy.orm import Session

from app.core.errors import NotFound, ValidationFailed
from app.models import Client, Project, User
from app.models.enums import BillingType, InvoiceStatus
from app.repositories import analytics as repo
from app.schemas.analytics import (
    Balance,
    Breakdown,
    BreakdownRow,
    CurrencyRate,
    DashboardSummary,
    DateRange,
    GroupBy,
    Interval,
    InvoiceCounts,
    MoneyFlow,
    Period,
    ProjectMoney,
    ProjectSlice,
    ProjectSummary,
    ResolvedRateOut,
    SeriesPoint,
    TaskSlice,
    Timeseries,
)
from app.schemas.common import currency_amounts
from app.services.invoices import local_today
from app.services.money import ZERO, effective_hourly_rate
from app.services.time_entries import local_day_bounds, resolve_rate

MAX_RANGE_DAYS = 366
TOP_PROJECTS = 5


# ---------------------------------------------------------------- ranges


def week_start_of(day: date, week_start: int) -> date:
    """week_start uses ISO weekday numbers: 1 = Monday … 7 = Sunday."""
    return day - timedelta(days=(day.isoweekday() - week_start) % 7)


def _month_end(day: date) -> date:
    first_next = (day.replace(day=28) + timedelta(days=4)).replace(day=1)
    return first_next - timedelta(days=1)


def _add_months(day: date, months: int) -> date:
    index = day.year * 12 + day.month - 1 + months
    return date(index // 12, index % 12 + 1, 1)


def period_range(period: Period, today: date, week_start: int) -> tuple[date, date]:
    if period == "today":
        return today, today
    if period == "week":
        start = week_start_of(today, week_start)
        return start, start + timedelta(days=6)
    if period == "month":
        return today.replace(day=1), _month_end(today)
    if period == "quarter":
        start = date(today.year, (today.month - 1) // 3 * 3 + 1, 1)
        return start, _month_end(_add_months(start, 2))
    return date(today.year, 1, 1), date(today.year, 12, 31)


def previous_range(period: Period | None, lo: date, hi: date) -> tuple[date, date]:
    """Calendar periods compare with the previous calendar period; custom ranges with the same length."""
    if period in ("month", "quarter", "year"):
        months = {"month": 1, "quarter": 3, "year": 12}[period]
        start = _add_months(lo, -months)
        return start, lo - timedelta(days=1)
    length = (hi - lo).days + 1
    return lo - timedelta(days=length), lo - timedelta(days=1)


def resolve_range(
    user: User, now: datetime, period: Period | None, day_from: date | None, day_to: date | None
) -> tuple[date, date, Period | None]:
    today = local_today(user, now)
    if day_from or day_to:
        hi = day_to or today
        lo = day_from or hi
        if hi < lo:
            raise ValidationFailed("'to' must not be before 'from'.", field="to", code="invalid_range")
        if (hi - lo).days >= MAX_RANGE_DAYS:
            raise ValidationFailed("Range is limited to one year.", field="to", code="range_too_long")
        return lo, hi, None
    chosen: Period = period or "month"
    lo, hi = period_range(chosen, today, user.week_start)
    return lo, hi, chosen


def _date_range(lo: date, hi: date) -> DateRange:
    return DateRange(from_=lo, to=hi)


# ---------------------------------------------------------------- dashboard


@dataclass
class _Acc:
    seconds: int = 0
    billable: int = 0
    priced: int = 0
    entries: int = 0
    amounts: dict[str, Decimal] = field(default_factory=lambda: defaultdict(lambda: ZERO))
    priced_by_currency: dict[str, int] = field(default_factory=lambda: defaultdict(int))
    billable_by_currency: dict[str, int] = field(default_factory=lambda: defaultdict(int))


def _accumulate(rows: list[tuple[date, str, int, int, int, Decimal | None, int]]) -> _Acc:
    acc = _Acc()
    for _day, currency, seconds, billable, priced, amount, entries in rows:
        acc.seconds += seconds
        acc.billable += billable
        acc.priced += priced
        acc.entries += entries
        acc.priced_by_currency[currency] += priced
        acc.billable_by_currency[currency] += billable
        if amount is not None:
            acc.amounts[currency] += amount
    return acc


def dashboard(
    db: Session, user: User, *, period: Period | None, day_from: date | None, day_to: date | None, now: datetime
) -> DashboardSummary:
    lo, hi, chosen = resolve_range(user, now, period, day_from, day_to)
    prev_lo, prev_hi = previous_range(chosen, lo, hi)
    current = _accumulate(repo.daily(db, user.id, user.timezone, *local_day_bounds(lo, hi, user.timezone)))
    previous = _accumulate(repo.daily(db, user.id, user.timezone, *local_day_bounds(prev_lo, prev_hi, user.timezone)))
    invoiced = repo.invoiced_by_currency(db, user.id, lo, hi)
    received: dict[str, Decimal] = defaultdict(lambda: ZERO)
    for _day, currency, amount in repo.payments_daily(db, user.id, lo, hi):
        received[currency] += amount

    currencies = sorted(set(current.amounts) | set(previous.amounts) | set(invoiced) | set(received))
    flows = [
        MoneyFlow(
            currency=c,
            tracked=current.amounts.get(c, ZERO),
            previous_tracked=previous.amounts.get(c, ZERO),
            invoiced=invoiced.get(c, ZERO),
            received=received.get(c, ZERO),
            billable_seconds=current.billable_by_currency.get(c, 0),
            effective_hourly_rate=effective_hourly_rate(
                current.amounts.get(c, ZERO), current.priced_by_currency.get(c, 0)
            ),
        )
        for c in currencies
    ]
    flows.sort(key=lambda f: (-f.tracked, -f.received, f.currency))

    return DashboardSummary(
        range=_date_range(lo, hi),
        previous_range=_date_range(prev_lo, prev_hi),
        tracked_seconds=current.seconds,
        billable_seconds=current.billable,
        previous_tracked_seconds=previous.seconds,
        entries=current.entries,
        flows=flows,
        balances=balances(db, user, now),
        invoices=_invoice_counts(db, user, now),
        top_projects=_top_projects(db, user, lo, hi),
        server_time=now,
    )


def balances(db: Session, user: User, now: datetime) -> list[Balance]:
    today = local_today(user, now)
    unbilled = repo.unbilled_by_currency(db, user.id)
    outstanding: dict[str, Decimal] = defaultdict(lambda: ZERO)
    overdue: dict[str, Decimal] = defaultdict(lambda: ZERO)
    for currency, due_date, total, paid in repo.open_invoices(db, user.id):
        open_amount = total - paid
        outstanding[currency] += open_amount
        if due_date < today:
            overdue[currency] += open_amount
    rows = [
        Balance(
            currency=c,
            unbilled=unbilled.get(c, ZERO),
            outstanding=outstanding.get(c, ZERO),
            overdue=overdue.get(c, ZERO),
        )
        for c in set(unbilled) | set(outstanding)
    ]
    rows = [b for b in rows if b.unbilled or b.outstanding]
    return sorted(rows, key=lambda b: (-(b.unbilled + b.outstanding), b.currency))


def _invoice_counts(db: Session, user: User, now: datetime) -> InvoiceCounts:
    counts = repo.invoice_status_counts(db, user.id)
    today = local_today(user, now)
    overdue = sum(1 for _c, due_date, _t, _p in repo.open_invoices(db, user.id) if due_date < today)
    return InvoiceCounts(
        draft=counts.get(InvoiceStatus.draft, 0), open=counts.get(InvoiceStatus.sent, 0), overdue=overdue
    )


def _top_projects(db: Session, user: User, lo: date, hi: date) -> list[ProjectSlice]:
    grouped: dict[uuid.UUID, tuple[Project, str, int, dict[str, Decimal]]] = {}
    for project, client_name, currency, seconds, _b, _p, amount in repo.by_project(
        db, user.id, *local_day_bounds(lo, hi, user.timezone)
    ):
        _, _, total, amounts = grouped.get(project.id, (project, client_name, 0, {}))
        if amount is not None:
            amounts[currency] = amounts.get(currency, ZERO) + amount
        grouped[project.id] = (project, client_name, total + seconds, amounts)
    ranked = sorted(grouped.values(), key=lambda g: (-g[2], g[0].name.lower()))[:TOP_PROJECTS]
    return [
        ProjectSlice(
            id=p.id,
            name=p.name,
            color=p.color,
            client_name=client_name,
            seconds=seconds,
            amounts=currency_amounts(amounts),
        )
        for p, client_name, seconds, amounts in ranked
        if seconds > 0
    ]


# ---------------------------------------------------------------- timeseries


def bucket_start(day: date, interval: Interval, week_start: int) -> date:
    if interval == "day":
        return day
    if interval == "week":
        return week_start_of(day, week_start)
    return day.replace(day=1)


def _next_bucket(start: date, interval: Interval) -> date:
    if interval == "day":
        return start + timedelta(days=1)
    if interval == "week":
        return start + timedelta(days=7)
    return _add_months(start, 1)


def timeseries(
    db: Session,
    user: User,
    *,
    period: Period | None,
    day_from: date | None,
    day_to: date | None,
    interval: Interval | None,
    now: datetime,
) -> Timeseries:
    lo, hi, _ = resolve_range(user, now, period, day_from, day_to)
    span = (hi - lo).days + 1
    chosen: Interval = interval or ("day" if span <= 31 else "week" if span <= 120 else "month")

    tracked: dict[date, _Acc] = defaultdict(_Acc)
    for day, currency, seconds, billable, priced, amount, entries in repo.daily(
        db, user.id, user.timezone, *local_day_bounds(lo, hi, user.timezone)
    ):
        acc = tracked[bucket_start(day, chosen, user.week_start)]
        acc.seconds += seconds
        acc.billable += billable
        acc.priced += priced
        acc.entries += entries
        if amount is not None:
            acc.amounts[currency] += amount
    received: dict[date, dict[str, Decimal]] = defaultdict(lambda: defaultdict(lambda: ZERO))
    for day, currency, amount in repo.payments_daily(db, user.id, lo, hi):
        received[bucket_start(day, chosen, user.week_start)][currency] += amount

    points: list[SeriesPoint] = []
    start = bucket_start(lo, chosen, user.week_start)
    while start <= hi:
        nxt = _next_bucket(start, chosen)
        acc = tracked.get(start, _Acc())
        points.append(
            SeriesPoint(
                start=max(start, lo),
                end=min(nxt - timedelta(days=1), hi),
                seconds=acc.seconds,
                billable_seconds=acc.billable,
                tracked=currency_amounts(dict(acc.amounts)),
                received=currency_amounts(dict(received.get(start, {}))),
            )
        )
        start = nxt
    return Timeseries(range=_date_range(lo, hi), interval=chosen, points=points)


# ---------------------------------------------------------------- breakdown


def _rates(amounts: dict[str, Decimal], priced: dict[str, int]) -> list[CurrencyRate]:
    rates = []
    for currency, amount in amounts.items():
        rate = effective_hourly_rate(amount, priced.get(currency, 0))
        if rate is not None:
            rates.append(CurrencyRate(currency=currency, rate=rate))
    return sorted(rates, key=lambda r: r.currency)


def _fixed_rate(project: Project, all_time_seconds: int) -> list[CurrencyRate]:
    if project.fixed_fee is None:
        return []
    rate = effective_hourly_rate(project.fixed_fee, all_time_seconds)
    return [CurrencyRate(currency=project.currency, rate=rate)] if rate is not None else []


@dataclass
class _Row:
    seconds: int = 0
    billable: int = 0
    amounts: dict[str, Decimal] = field(default_factory=dict)
    priced: dict[str, int] = field(default_factory=dict)

    def add(self, currency: str, seconds: int, billable: int, priced: int, amount: Decimal | None) -> None:
        self.seconds += seconds
        self.billable += billable
        self.priced[currency] = self.priced.get(currency, 0) + priced
        if amount is not None:
            self.amounts[currency] = self.amounts.get(currency, ZERO) + amount


def breakdown(
    db: Session,
    user: User,
    *,
    period: Period | None,
    day_from: date | None,
    day_to: date | None,
    group_by: GroupBy,
    now: datetime,
) -> Breakdown:
    lo, hi, _ = resolve_range(user, now, period, day_from, day_to)
    start, end = local_day_bounds(lo, hi, user.timezone)
    rows: list[BreakdownRow] = []
    if group_by == "project":
        acc: dict[uuid.UUID, tuple[Project, str, _Row]] = {}
        for project, client_name, currency, seconds, billable, priced, amount in repo.by_project(
            db, user.id, start, end
        ):
            row = acc.setdefault(project.id, (project, client_name, _Row()))[2]
            row.add(currency, seconds, billable, priced, amount)
        fixed_ids = [p.id for p, _, _ in acc.values() if p.billing_type is BillingType.fixed]
        all_time = repo.project_seconds_all_time(db, user.id, fixed_ids)
        for project, client_name, row in acc.values():
            fixed = project.billing_type is BillingType.fixed
            rows.append(
                BreakdownRow(
                    id=project.id,
                    name=project.name,
                    color=project.color,
                    client_name=client_name,
                    billing_type=project.billing_type,
                    seconds=row.seconds,
                    billable_seconds=row.billable,
                    share=0.0,
                    amounts=currency_amounts(row.amounts),
                    effective_hourly_rate=(
                        _fixed_rate(project, all_time.get(project.id, 0)) if fixed else _rates(row.amounts, row.priced)
                    ),
                )
            )
    else:
        by_client: dict[uuid.UUID, tuple[Client, _Row]] = {}
        for client, currency, seconds, billable, priced, amount in repo.by_client(db, user.id, start, end):
            row = by_client.setdefault(client.id, (client, _Row()))[1]
            row.add(currency, seconds, billable, priced, amount)
        for client, row in by_client.values():
            rows.append(
                BreakdownRow(
                    id=client.id,
                    name=client.name,
                    color=None,
                    client_name=None,
                    billing_type=None,
                    seconds=row.seconds,
                    billable_seconds=row.billable,
                    share=0.0,
                    amounts=currency_amounts(row.amounts),
                    effective_hourly_rate=_rates(row.amounts, row.priced),
                )
            )

    total = sum(r.seconds for r in rows)
    for r in rows:
        r.share = round(r.seconds / total, 4) if total else 0.0
    rows.sort(key=lambda r: (-r.seconds, r.name.lower()))
    return Breakdown(range=_date_range(lo, hi), group_by=group_by, total_seconds=total, rows=rows)


# ---------------------------------------------------------------- project summary


def project_summary(db: Session, user: User, project_id: uuid.UUID, now: datetime) -> ProjectSummary:
    project = db.get(Project, project_id)
    if project is None or project.user_id != user.id:
        raise NotFound("Project not found.")
    client = db.get(Client, project.client_id)
    rate = resolve_rate(project, client, user)

    rows = repo.project_money(db, user.id, project.id)
    seconds = sum(r[1] for r in rows)
    billable = sum(r[2] for r in rows)
    entries = sum(r[4] for r in rows)
    first = min((r[7] for r in rows), default=None)
    last = max((r[8] for r in rows), default=None)
    money: list[ProjectMoney] = []
    amounts: dict[str, Decimal] = {}
    priced: dict[str, int] = {}
    for currency, _s, _b, priced_s, _n, tracked, unbilled, _lo, _hi in rows:
        if tracked is None:
            continue
        amounts[currency] = tracked
        priced[currency] = priced_s
        unbilled_amount = unbilled if unbilled is not None else ZERO
        money.append(
            ProjectMoney(
                currency=currency, tracked=tracked, unbilled=unbilled_amount, invoiced=tracked - unbilled_amount
            )
        )
    money.sort(key=lambda m: (-m.tracked, m.currency))

    tasks: dict[uuid.UUID | None, tuple[str | None, int, dict[str, Decimal]]] = {}
    for task_id, title, currency, task_seconds, amount in repo.project_by_task(db, user.id, project.id):
        t_title, total, task_amounts = tasks.get(task_id, (title, 0, {}))
        if amount is not None:
            task_amounts[currency] = task_amounts.get(currency, ZERO) + amount
        tasks[task_id] = (t_title, total + task_seconds, task_amounts)
    by_task = sorted(
        (
            TaskSlice(task_id=tid, title=title, seconds=s, amounts=currency_amounts(a))
            for tid, (title, s, a) in tasks.items()
        ),
        key=lambda t: (-t.seconds, t.title or ""),
    )

    fixed = project.billing_type is BillingType.fixed
    since = now - timedelta(days=30)
    budget = project.budget_hours
    return ProjectSummary(
        project_id=project.id,
        billing_type=project.billing_type,
        currency=project.currency,
        tracked_seconds=seconds,
        billable_seconds=billable,
        entries=entries,
        first_entry_at=first,
        last_entry_at=last,
        budget_hours=budget,
        budget_used=round(seconds / 3600 / float(budget), 4) if budget else None,
        fixed_fee=project.fixed_fee,
        current_rate=ResolvedRateOut(rate=rate.rate, currency=rate.currency, source=rate.source.value),
        effective_hourly_rate=_fixed_rate(project, seconds) if fixed else _rates(amounts, priced),
        money=money,
        by_task=by_task,
        last_30_days_seconds=repo.project_seconds_since(db, user.id, project.id, since),
    )
