"""Demo account for screenshots, screencasts and portfolio reviews.

    python -m app.cli.seed_demo                    # demo@freelancehub.app / FreelanceHub-demo-2026
    python -m app.cli.seed_demo --email you@x.com  # another address

Everything goes through the same services as the API (rate snapshots, rounding, invoice rules, numbering), so
every figure in the app is computed by the real business logic — nothing is written to the tables directly.
The data is generated relative to *today* in the demo user's time zone with a fixed random seed, so re-running
gives the same shape of history ending today. Re-running deletes and recreates only the demo user.

Refuses to run with ENVIRONMENT=production unless --force is given.
"""

import argparse
import random
import sys
import uuid
from dataclasses import dataclass
from datetime import UTC, date, datetime, time, timedelta
from decimal import Decimal
from zoneinfo import ZoneInfo

from sqlalchemy import delete, select, update
from sqlalchemy.orm import Session

from app.core.clock import Clock, utc_now
from app.core.config import get_settings
from app.db.session import get_session_factory
from app.models import Invoice, Payment, TimeEntry, User
from app.schemas.auth import RegisterRequest
from app.schemas.clients import ClientCreate
from app.schemas.invoices import InvoiceCreate, PaymentCreate
from app.schemas.projects import ProjectCreate
from app.schemas.tasks import TaskCreate
from app.schemas.time_entries import ManualEntryCreate, TimerStart
from app.services import auth as auth_service
from app.services import clients as clients_service
from app.services import invoices as invoices_service
from app.services import projects as projects_service
from app.services import tasks as tasks_service
from app.services import time_entries as entries_service

DEFAULT_EMAIL = "demo@freelancehub.app"
DEFAULT_PASSWORD = "FreelanceHub-demo-2026"  # noqa: S105 - public demo-only account, printed on purpose
TIMEZONE = "Europe/Kyiv"
HISTORY_DAYS = 75


@dataclass
class ProjectSpec:
    key: str
    client: str
    name: str
    color: str
    billing: str = "hourly"
    rate: str | None = None
    fixed_fee: str | None = None
    budget_hours: str | None = None
    weight: int = 1
    tasks: tuple[tuple[str, str], ...] = ()
    work: tuple[str, ...] = ()


CLIENTS = [
    {
        "name": "Northwind Labs",
        "company": "Northwind Labs Inc.",
        "email": "billing@northwind.example",
        "currency": "USD",
        "default_hourly_rate": "85.00",
    },
    {
        "name": "Brightside Studio",
        "company": "Brightside Studio GmbH",
        "email": "hello@brightside.example",
        "currency": "EUR",
        "default_hourly_rate": "70.00",
    },
    {
        "name": "Acme Logistics",
        "company": "Acme Logistics LLC",
        "email": "ap@acme-logistics.example",
        "currency": "USD",
        "default_hourly_rate": "90.00",
    },
    {
        "name": "Lumen Health",
        "company": "Lumen Health Ltd",
        "email": "finance@lumen.example",
        "currency": "USD",
        "default_hourly_rate": "100.00",
    },
]

PROJECTS = [
    ProjectSpec(
        "bank",
        "Northwind Labs",
        "Mobile banking app",
        "#8B7CFF",
        rate="95.00",
        budget_hours="160",
        weight=5,
        tasks=(
            ("Biometric sign-in", "done"),
            ("Transfers flow", "in_progress"),
            ("Push notifications", "todo"),
            ("Offline cache", "todo"),
        ),
        work=(
            "Transfers flow: review form",
            "Biometric sign-in on Android",
            "Fix keyboard overlap on iOS",
            "Code review and PR fixes",
            "Push notification handlers",
            "Offline cache for accounts list",
            "Sprint planning call",
        ),
    ),
    ProjectSpec(
        "api",
        "Northwind Labs",
        "Partner API integration",
        "#5B8DEF",
        weight=2,
        tasks=(("OAuth client credentials", "done"), ("Webhook retries", "in_progress")),
        work=("Webhook retry policy", "OAuth token rotation", "Contract tests for partner API", "Rate-limit handling"),
    ),
    ProjectSpec(
        "site",
        "Brightside Studio",
        "Marketing website",
        "#F2994A",
        billing="fixed",
        fixed_fee="4800.00",
        budget_hours="60",
        weight=2,
        tasks=(("Landing page", "done"), ("Blog CMS", "in_progress"), ("SEO audit", "todo")),
        work=("Landing page animations", "Blog CMS integration", "Lighthouse performance pass", "Content migration"),
    ),
    ProjectSpec(
        "ds",
        "Brightside Studio",
        "Design system",
        "#EB5757",
        rate="75.00",
        weight=2,
        tasks=(("Tokens and theming", "done"), ("Component docs", "in_progress")),
        work=(
            "Button and input components",
            "Theme tokens in Figma and code",
            "Storybook docs",
            "Accessibility review",
        ),
    ),
    ProjectSpec(
        "fleet",
        "Acme Logistics",
        "Fleet dashboard",
        "#27AE60",
        budget_hours="90",
        weight=3,
        tasks=(("Live vehicle map", "done"), ("Route analytics", "in_progress"), ("CSV export", "todo")),
        work=(
            "Live vehicle map",
            "Route analytics charts",
            "Driver shift report",
            "Postgres query tuning",
            "Weekly sync with ops team",
        ),
    ),
    ProjectSpec(
        "portal",
        "Lumen Health",
        "Patient portal",
        "#2D9CDB",
        rate="110.00",
        weight=2,
        tasks=(("Appointment booking", "in_progress"), ("Secure messaging", "todo")),
        work=("Appointment booking UI", "Secure messaging backend", "HIPAA checklist review", "E2E tests for booking"),
    ),
    ProjectSpec(
        "discovery",
        "Acme Logistics",
        "Discovery workshop",
        "#9B51E0",
        billing="non_billable",
        weight=1,
        work=("Discovery workshop prep", "Estimate for phase 2"),
    ),
]


class FixedClock:
    """The seed uses one 'now' for the whole run so every 'today' is consistent."""

    def __init__(self, now: datetime) -> None:
        self.now = now

    def __call__(self) -> datetime:
        return self.now


def _delete_user(db: Session, email: str) -> None:
    user = db.scalar(select(User).where(User.email == email))
    if user is None:
        return
    # Payments and invoices reference clients with RESTRICT, so they go first; the rest cascades from the user.
    db.execute(delete(Payment).where(Payment.user_id == user.id))
    db.execute(update(TimeEntry).where(TimeEntry.user_id == user.id).values(invoice_id=None))
    db.execute(delete(Invoice).where(Invoice.user_id == user.id))
    db.delete(user)
    db.flush()


def _work_days(today: date) -> list[date]:
    days = [today - timedelta(days=n) for n in range(HISTORY_DAYS, -1, -1)]
    return [d for d in days if d.weekday() < 5]


def _entries(
    db: Session,
    user: User,
    projects: dict[str, uuid.UUID],
    tasks: dict[str, list[uuid.UUID]],
    clock: Clock,
    rng: random.Random,
) -> None:
    tz = ZoneInfo(TIMEZONE)
    now = clock()
    today = now.astimezone(tz).date()
    keys = [p.key for p in PROJECTS for _ in range(p.weight)]
    work = {p.key: p.work for p in PROJECTS}
    for day in _work_days(today):
        cursor = datetime.combine(day, time(9, rng.choice([0, 15, 30])), tz)
        for n in range(rng.choice([2, 3, 3, 4])):
            # The last two working days start with the main project, so "this week" is never empty for it.
            key = "bank" if n == 0 and (today - day).days <= 2 else rng.choice(keys)
            minutes = rng.choice([25, 40, 55, 75, 90, 105, 120, 150, 180])
            seconds = minutes * 60 + rng.randint(0, 59)  # odd seconds exercise the rounding
            start, end = cursor, cursor + timedelta(seconds=seconds)
            # Today: stop early enough to leave room for the running timer (started 47 min ago).
            if end > now - timedelta(minutes=55) or end.hour >= 19:
                break
            entries_service.create_manual(
                db,
                user,
                ManualEntryCreate.model_validate(
                    {
                        "project_id": str(projects[key]),
                        "task_id": str(rng.choice(tasks[key])) if tasks[key] and rng.random() < 0.7 else None,
                        "description": rng.choice(work[key]),
                        "started_at": start.isoformat(),
                        "ended_at": end.isoformat(),
                    }
                ),
                clock,
            )
            cursor = end + timedelta(minutes=rng.choice([10, 20, 30, 45, 60]))


def _billable_ids(db: Session, user: User, project_ids: list[uuid.UUID], lo: date, hi: date) -> list[str]:
    start, end = entries_service.local_day_bounds(lo, hi, TIMEZONE)
    rows = db.scalars(
        select(TimeEntry.id)
        .where(
            TimeEntry.user_id == user.id,
            TimeEntry.project_id.in_(project_ids),
            TimeEntry.billable.is_(True),
            TimeEntry.billable_amount.is_not(None),
            TimeEntry.invoice_id.is_(None),
            TimeEntry.started_at >= start,
            TimeEntry.started_at < end,
        )
        .order_by(TimeEntry.started_at)
    )
    return [str(i) for i in rows]


def _invoice(
    db: Session,
    user: User,
    clock: Clock,
    client_id: uuid.UUID,
    issue: date,
    due_days: int,
    *,
    entry_ids: list[str] | None = None,
    items: list[dict[str, str]] | None = None,
    tax: str = "0",
    notes: str | None = None,
) -> Invoice:
    data = InvoiceCreate.model_validate(
        {
            "client_id": str(client_id),
            "issue_date": issue.isoformat(),
            "due_date": (issue + timedelta(days=due_days)).isoformat(),
            "tax_rate": tax,
            "notes": notes,
            "time_entry_ids": entry_ids or [],
            "items": items or [],
        }
    )
    return invoices_service.create(db, user, data, clock)


def _pay(
    db: Session, user: User, clock: Clock, invoice: Invoice, amount: Decimal | str, paid_on: date, method: str
) -> None:
    payload = {"amount": f"{Decimal(amount):.2f}", "paid_on": paid_on.isoformat(), "method": method}
    invoices_service.add_payment(db, user, invoice.id, PaymentCreate.model_validate(payload), clock)


def seed(
    db: Session, email: str = DEFAULT_EMAIL, password: str = DEFAULT_PASSWORD, *, now: datetime | None = None
) -> User:
    settings = get_settings()
    clock = FixedClock((now or utc_now()).astimezone(UTC))
    rng = random.Random(2026)  # noqa: S311 - deterministic demo data, not security
    _delete_user(db, email)
    db.commit()

    register = RegisterRequest.model_validate(
        {
            "email": email,
            "password": password,
            "full_name": "Alex Morgan",
            "timezone": TIMEZONE,
            "default_currency": "USD",
        }
    )
    tokens = auth_service.register(db, register, settings, "seed_demo")
    user = tokens.user
    user.default_hourly_rate = Decimal("60.00")

    client_ids = {
        c["name"]: clients_service.create_client(db, user, ClientCreate.model_validate(c)).id for c in CLIENTS
    }
    projects: dict[str, uuid.UUID] = {}
    tasks: dict[str, list[uuid.UUID]] = {}
    for p in PROJECTS:
        payload = {
            "client_id": str(client_ids[p.client]),
            "name": p.name,
            "color": p.color,
            "billing_type": p.billing,
            "hourly_rate": p.rate,
            "fixed_fee": p.fixed_fee,
            "budget_hours": p.budget_hours,
        }
        project = projects_service.create_project(
            db, user, ProjectCreate.model_validate({k: v for k, v in payload.items() if v is not None})
        )
        projects[p.key] = project.id
        tasks[p.key] = [
            tasks_service.create_task(
                db, user, TaskCreate.model_validate({"project_id": str(project.id), "title": title, "status": status})
            ).id
            for title, status in p.tasks
        ]

    _entries(db, user, projects, tasks, clock, rng)

    today = clock().astimezone(ZoneInfo(TIMEZONE)).date()
    month_start = today.replace(day=1)
    prev_month_end = month_start - timedelta(days=1)
    prev_month_start = prev_month_end.replace(day=1)
    two_ago_end = prev_month_start - timedelta(days=1)
    two_ago_start = two_ago_end.replace(day=1)
    northwind = [projects["bank"], projects["api"]]

    # 1) Paid in full: Northwind, the month before last.
    inv = _invoice(
        db,
        user,
        clock,
        client_ids["Northwind Labs"],
        two_ago_end + timedelta(days=1),
        14,
        entry_ids=_billable_ids(db, user, northwind, two_ago_start, two_ago_end),
        notes="Thank you for your business!",
    )
    invoices_service.send(db, user, inv.id, None, clock)
    _pay(db, user, clock, inv, inv.total, two_ago_end + timedelta(days=9), "bank_transfer")

    # 2) Acme, the month before last: sent with the wrong tax, voided (which releases the time) and re-issued.
    fleet_ids = _billable_ids(db, user, [projects["fleet"]], two_ago_start, two_ago_end)
    wrong = _invoice(
        db,
        user,
        clock,
        client_ids["Acme Logistics"],
        two_ago_end + timedelta(days=1),
        14,
        entry_ids=fleet_ids,
        tax="20",
    )
    invoices_service.send(db, user, wrong.id, None, clock)
    invoices_service.void(db, user, wrong.id, None, clock)
    # 3) The re-issued invoice is overdue: unpaid, and its due date passed weeks ago.
    overdue = _invoice(
        db,
        user,
        clock,
        client_ids["Acme Logistics"],
        two_ago_end + timedelta(days=3),
        14,
        entry_ids=fleet_ids,
        notes="Net 14. Bank details on page 2.",
    )
    invoices_service.send(db, user, overdue.id, None, clock)

    # 4) Fixed-fee milestone, part-paid and not due yet.
    milestone = _invoice(
        db,
        user,
        clock,
        client_ids["Brightside Studio"],
        today - timedelta(days=12),
        30,
        items=[
            {
                "description": "Marketing website: milestone 1 of 2 (design + landing)",
                "quantity": "1",
                "unit_price": "2400.00",
            }
        ],
        tax="19",
        notes="50 % now, 50 % on launch.",
    )
    invoices_service.send(db, user, milestone.id, None, clock)
    _pay(db, user, clock, milestone, "1500.00", today - timedelta(days=4), "bank_transfer")

    # 5) Northwind last month: sent on the 1st, net 30, open.
    nw = _invoice(
        db,
        user,
        clock,
        client_ids["Northwind Labs"],
        month_start,
        30,
        entry_ids=_billable_ids(db, user, northwind, two_ago_end + timedelta(days=1), prev_month_end),
    )
    invoices_service.send(db, user, nw.id, None, clock)

    # 6) Lumen Health: everything so far, paid by card on the spot.
    lumen = _invoice(
        db,
        user,
        clock,
        client_ids["Lumen Health"],
        prev_month_end + timedelta(days=1),
        7,
        entry_ids=_billable_ids(db, user, [projects["portal"]], two_ago_start, prev_month_end),
    )
    if lumen.items:
        invoices_service.send(db, user, lumen.id, None, clock)
        _pay(db, user, clock, lumen, lumen.total, min(prev_month_end + timedelta(days=3), today), "card")
    else:
        invoices_service.delete(db, user, lumen.id, clock)

    # 7) A draft for this month's Northwind work so far; the rest of this month stays unbilled.
    _invoice(
        db,
        user,
        clock,
        client_ids["Northwind Labs"],
        today,
        14,
        entry_ids=_billable_ids(db, user, [projects["bank"]], month_start, today - timedelta(days=1)),
        items=[{"description": "App Store submission support", "quantity": "1", "unit_price": "250.00"}],
    )

    # The running timer: the app opens with live time ticking.
    entries_service.start(
        db,
        user,
        TimerStart.model_validate(
            {
                "id": str(uuid.uuid4()),
                "project_id": str(projects["bank"]),
                "description": "Transfers flow: confirmation screen",
                "at": (clock() - timedelta(minutes=47)).isoformat(),
            }
        ),
        clock,
    )
    db.commit()
    return user


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--email", default=DEFAULT_EMAIL)
    parser.add_argument("--password", default=DEFAULT_PASSWORD)
    parser.add_argument("--force", action="store_true", help="allow ENVIRONMENT=production")
    args = parser.parse_args(argv)
    if get_settings().environment == "production" and not args.force:
        print("Refusing to seed demo data in production (use --force).", file=sys.stderr)
        return 2
    with get_session_factory()() as db:
        user = seed(db, args.email, args.password)
        n_entries = len(list(db.scalars(select(TimeEntry.id).where(TimeEntry.user_id == user.id))))
        n_invoices = len(list(db.scalars(select(Invoice.id).where(Invoice.user_id == user.id))))
    print(f"Demo account ready: {args.email} / {args.password}")
    print(
        f"  {len(CLIENTS)} clients, {len(PROJECTS)} projects, {n_entries} time entries, "
        f"{n_invoices} invoices, 1 running timer"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
