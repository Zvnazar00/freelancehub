"""The demo seed builds a believable account through the real services, on any day it is run."""

from datetime import UTC, datetime

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.cli.seed_demo import DEFAULT_EMAIL, DEFAULT_PASSWORD, seed
from app.models import Invoice, TimeEntry, User
from tests.conftest import FakeClock

API = "/api/v1"


def _login(client: TestClient) -> dict[str, str]:
    r = client.post(f"{API}/auth/login", json={"email": DEFAULT_EMAIL, "password": DEFAULT_PASSWORD})
    assert r.status_code == 200, r.text
    return {"Authorization": f"Bearer {r.json()['access_token']}"}


@pytest.mark.parametrize(
    "now",
    [
        datetime(2026, 10, 13, 15, 30, tzinfo=UTC),  # a Tuesday afternoon mid-month
        datetime(2026, 11, 1, 6, 0, tzinfo=UTC),  # Sunday morning, first day of the month
        datetime(2027, 1, 2, 23, 0, tzinfo=UTC),  # just after New Year in Kyiv (numbering by issue year)
    ],
)
def test_seed_covers_every_state_on_any_day(db: Session, client: TestClient, clock: FakeClock, now: datetime) -> None:
    clock.set(now)
    seed(db, now=now)
    seed(db, now=now)  # re-running replaces the demo user instead of failing or duplicating
    assert db.scalar(select(func.count()).select_from(User).where(User.email == DEFAULT_EMAIL)) == 1

    headers = _login(client)
    invoices = client.get(f"{API}/invoices", headers=headers).json()["items"]
    states = {(i["status"], i["payment_status"], i["is_overdue"]) for i in invoices}
    assert ("paid", "paid", False) in states
    assert ("void", None, False) in states
    assert ("sent", "unpaid", True) in states  # overdue
    assert ("sent", "partial", False) in states
    assert ("draft", None, False) in states
    numbers = sorted(i["number"] for i in invoices if i["number"])
    assert len(numbers) == len(set(numbers))  # gapless and unique per year, assigned on send

    timer = client.get(f"{API}/timer/current", headers=headers).json()["entry"]
    assert timer["status"] == "running" and timer["elapsed_seconds"] == 47 * 60

    summary = client.get(f"{API}/dashboard/summary?period=quarter", headers=headers).json()
    currencies = {f["currency"] for f in summary["flows"]}
    assert currencies == {"USD", "EUR"}  # two currencies, never added together
    balances = {b["currency"]: b for b in summary["balances"]}
    assert balances["USD"]["overdue"] != "0.00" and balances["USD"]["unbilled"] != "0.00"

    user = db.scalar(select(User).where(User.email == DEFAULT_EMAIL))
    assert user is not None
    entries = db.scalar(select(func.count()).select_from(TimeEntry).where(TimeEntry.user_id == user.id))
    assert entries is not None and entries > 100
    for inv in db.scalars(select(Invoice).where(Invoice.user_id == user.id)):
        assert inv.total == inv.subtotal + inv.tax_amount
        assert inv.subtotal == sum((item.amount for item in inv.items), start=inv.subtotal * 0)
