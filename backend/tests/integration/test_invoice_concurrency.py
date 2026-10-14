"""Real-concurrency races for invoices (real commits, one TestClient per thread, released together)."""

from typing import Any

from fastapi.testclient import TestClient
from sqlalchemy import Engine, select
from sqlalchemy.orm import Session

from app.models import Invoice, Payment
from tests.conftest import register
from tests.helpers import create_invoice, entry_at, make_client, make_project, new_key
from tests.integration.test_timer_concurrency import live, race  # noqa: F401  (fixture re-export)

API = "/api/v1"


def test_two_drafts_racing_for_the_same_entries_one_wins(live: Any, engine: Engine) -> None:  # noqa: F811
    with TestClient(live) as c:
        user = register(c, "race-invoice@example.com")
        client = make_client(c, user, "Acme")
        project = make_project(c, user, client["id"], "App", hourly_rate="50.00")
        ids = [entry_at(c, user, project["id"], f"2026-10-0{d}T09:00:00+00:00", 60)["id"] for d in (1, 2, 3)]

    def attempt(_: int) -> int:
        with TestClient(live) as tc:
            return int(create_invoice(tc, user, client["id"], time_entry_ids=ids).status_code)

    codes = race(6, attempt)
    assert sorted(codes) == [201] + [409] * 5
    with Session(engine) as s:
        assert len(list(s.scalars(select(Invoice)))) == 1


def test_concurrent_sends_get_distinct_consecutive_numbers(live: Any, engine: Engine) -> None:  # noqa: F811
    with TestClient(live) as c:
        user = register(c, "race-numbers@example.com")
        client = make_client(c, user, "Acme")
        drafts = [
            create_invoice(c, user, client["id"], items=[{"description": f"Line {i}", "unit_price": "10.00"}]).json()
            for i in range(5)
        ]

    def send(i: int) -> str:
        with TestClient(live) as tc:
            r = tc.post(f"{API}/invoices/{drafts[i]['id']}/send", headers=user.headers)
            assert r.status_code == 200, r.text
            return str(r.json()["number"])

    numbers = race(5, send)
    assert sorted(numbers) == [f"INV-2026-000{i}" for i in range(1, 6)]


def test_concurrent_payments_never_exceed_the_total(live: Any, engine: Engine) -> None:  # noqa: F811
    with TestClient(live) as c:
        user = register(c, "race-pay@example.com")
        client = make_client(c, user, "Acme")
        inv = create_invoice(c, user, client["id"], items=[{"description": "Work", "unit_price": "100.00"}]).json()
        c.post(f"{API}/invoices/{inv['id']}/send", headers=user.headers)

    def pay(_: int) -> int:
        with TestClient(live) as tc:
            r = tc.post(
                f"{API}/invoices/{inv['id']}/payments",
                json={"amount": "40.00"},
                headers={**user.headers, "Idempotency-Key": new_key()},
            )
            return int(r.status_code)

    codes = race(4, pay)
    assert sorted(codes) == [201, 201, 422, 422]  # the third and fourth would overpay (OVERPAYMENT)
    with Session(engine) as s:
        total = sum(p.amount for p in s.scalars(select(Payment)))
    assert total == 80
