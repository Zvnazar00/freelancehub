"""CSV exports: encoding, local times, money strings, billing status, formula-injection guard."""

import csv
import io

from fastapi.testclient import TestClient

from app.services.exports import INVOICE_COLUMNS, TIME_ENTRY_COLUMNS, safe_text
from tests.conftest import AuthedUser, register
from tests.helpers import assert_problem, create_invoice, entry_at, make_client, make_project

API = "/api/v1"


def _rows(body: bytes) -> list[dict[str, str]]:
    assert body.startswith("﻿".encode())  # BOM for Excel
    return list(csv.DictReader(io.StringIO(body.decode("utf-8-sig"))))


def test_time_entries_csv(client: TestClient) -> None:
    user = register(client, "csv@example.com", timezone="Europe/Kyiv")
    c = make_client(client, user, "=HYPERLINK(evil)", currency="EUR")
    p = make_project(client, user, c["id"], "Сайт", hourly_rate="60.00")
    billed = entry_at(client, user, p["id"], "2026-10-05T06:00:00+00:00", 90, description="+cmd|' /C calc'!A0")
    entry_at(client, user, p["id"], "2026-10-11T22:30:00+00:00", 20)  # local Oct 12, 01:30
    entry_at(client, user, p["id"], "2026-10-06T06:00:00+00:00", 30, billable=False)
    inv = create_invoice(client, user, c["id"], time_entry_ids=[billed["id"]]).json()
    client.post(f"{API}/invoices/{inv['id']}/send", headers=user.headers)

    r = client.get(
        f"{API}/exports/time-entries.csv", params={"from": "2026-10-01", "to": "2026-10-12"}, headers=user.headers
    )
    assert r.status_code == 200 and r.headers["content-type"] == "text/csv; charset=utf-8"
    assert 'filename="time-entries_2026-10-01_2026-10-12.csv"' in r.headers["content-disposition"]
    rows = _rows(r.content)
    assert list(rows[0].keys()) == TIME_ENTRY_COLUMNS
    assert [(x["date"], x["start"], x["end"]) for x in rows] == [
        ("2026-10-05", "09:00", "10:30"),
        ("2026-10-06", "09:00", "09:30"),
        ("2026-10-12", "01:30", "01:50"),
    ]
    first = rows[0]
    assert first["client"] == "'=HYPERLINK(evil)" and first["description"].startswith("'+cmd")
    assert first["project"] == "Сайт" and first["duration_hours"] == "1.50" and first["duration_seconds"] == "5400"
    assert (first["rate"], first["currency"], first["amount"]) == ("60.00", "EUR", "90.00")
    assert (first["billing_status"], first["invoice_number"]) == ("invoiced", "INV-2026-0001")
    assert rows[1]["billing_status"] == "not_billable" and rows[1]["amount"] == ""
    assert rows[2]["billing_status"] == "unbilled" and rows[2]["amount"] == "20.00"

    only_other = client.get(
        f"{API}/exports/time-entries.csv",
        params={"from": "2026-10-01", "to": "2026-10-12", "client_id": "00000000-0000-4000-8000-000000000000"},
        headers=user.headers,
    )
    assert _rows(only_other.content) == []


def test_invoices_csv_excludes_drafts(client: TestClient, alice: AuthedUser) -> None:
    c = make_client(client, alice, "Acme", currency="USD")
    sent = create_invoice(client, alice, c["id"], items=[{"description": "Work", "unit_price": "100.00"}]).json()
    create_invoice(client, alice, c["id"], items=[{"description": "Draft", "unit_price": "5.00"}])
    client.post(f"{API}/invoices/{sent['id']}/send", headers=alice.headers)
    r = client.get(
        f"{API}/exports/invoices.csv", params={"from": "2026-10-01", "to": "2026-10-31"}, headers=alice.headers
    )
    rows = _rows(r.content)
    assert list(rows[0].keys()) == INVOICE_COLUMNS
    assert [(x["number"], x["status"], x["payment_status"], x["total"], x["due"]) for x in rows] == [
        ("INV-2026-0001", "sent", "unpaid", "100.00", "100.00")
    ]


def test_export_range_rules_and_privacy(client: TestClient, alice: AuthedUser, bob: AuthedUser) -> None:
    c = make_client(client, alice, "Acme")
    p = make_project(client, alice, c["id"], "App", hourly_rate="50.00")
    entry_at(client, alice, p["id"], "2026-10-05T09:00:00+00:00", 60)
    default = client.get(f"{API}/exports/time-entries.csv", headers=alice.headers)  # month to date
    assert 'filename="time-entries_2026-10-01_2026-10-12.csv"' in default.headers["content-disposition"]
    assert len(_rows(default.content)) == 1
    assert _rows(client.get(f"{API}/exports/time-entries.csv", headers=bob.headers).content) == []
    too_long = client.get(
        f"{API}/exports/time-entries.csv", params={"from": "2025-01-01", "to": "2026-10-01"}, headers=alice.headers
    )
    assert_problem(too_long, 422, "VALIDATION_ERROR")
    assert client.get(f"{API}/exports/invoices.csv").status_code == 401


def test_safe_text() -> None:
    assert [safe_text(v) for v in ("=1+1", "+1", "-1", "@SUM", "\tx", "ok", "", None)] == [
        "'=1+1",
        "'+1",
        "'-1",
        "'@SUM",
        "'\tx",
        "ok",
        "",
        "",
    ]
