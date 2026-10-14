"""Dashboard, analytics and project summaries: money states, currencies, time zones, DST, ranges."""

from datetime import UTC, datetime
from typing import Any

from fastapi.testclient import TestClient

from tests.conftest import AuthedUser, FakeClock, register
from tests.helpers import assert_problem, create_invoice, entry_at, make_client, make_project, make_task, new_key

API = "/api/v1"


def _get(client: TestClient, user: AuthedUser, path: str, **params: Any) -> dict[str, Any]:
    r = client.get(f"{API}{path}", params=params, headers=user.headers)
    assert r.status_code == 200, r.text
    return r.json()  # type: ignore[no-any-return]


def _flow(summary: dict[str, Any], currency: str) -> dict[str, Any]:
    return next(f for f in summary["flows"] if f["currency"] == currency)


def test_tracked_invoiced_and_received_are_separate(client: TestClient, alice: AuthedUser) -> None:
    usd = make_client(client, alice, "Acme", currency="USD")
    eur = make_client(client, alice, "Bauhaus", currency="EUR")
    p_usd = make_project(client, alice, usd["id"], "App", hourly_rate="85.00")
    p_eur = make_project(client, alice, eur["id"], "Site", hourly_rate="60.00")
    e1 = entry_at(client, alice, p_usd["id"], "2026-10-05T09:00:00+00:00", 90)  # 127.50 USD
    entry_at(client, alice, p_usd["id"], "2026-10-06T09:00:00+00:00", 20)  # 28.33 USD
    entry_at(client, alice, p_eur["id"], "2026-10-07T09:00:00+00:00", 30)  # 30.00 EUR
    entry_at(client, alice, p_usd["id"], "2026-10-08T09:00:00+00:00", 60, billable=False)

    empty = _get(client, alice, "/dashboard/summary", period="month")
    assert {b["currency"]: b["unbilled"] for b in empty["balances"]} == {"USD": "155.83", "EUR": "30.00"}
    usd_flow = _flow(empty, "USD")
    assert usd_flow["tracked"] == "155.83" and usd_flow["invoiced"] == "0.00" and usd_flow["received"] == "0.00"
    assert usd_flow["effective_hourly_rate"] == "85.00"  # 155.83 / (110 min) = 84.998… → 85.00
    assert _flow(empty, "EUR")["tracked"] == "30.00"  # never added to USD
    assert empty["tracked_seconds"] == (90 + 20 + 30 + 60) * 60
    assert empty["billable_seconds"] == (90 + 20 + 30) * 60
    assert empty["range"] == {"from": "2026-10-01", "to": "2026-10-31"}
    assert empty["previous_range"] == {"from": "2026-09-01", "to": "2026-09-30"}

    inv = create_invoice(client, alice, usd["id"], time_entry_ids=[e1["id"]]).json()
    client.post(f"{API}/invoices/{inv['id']}/send", headers=alice.headers)
    client.post(
        f"{API}/invoices/{inv['id']}/payments",
        json={"amount": "100.00"},
        headers={**alice.headers, "Idempotency-Key": new_key()},
    )

    after = _get(client, alice, "/dashboard/summary", period="month")
    usd_flow = _flow(after, "USD")
    assert usd_flow["tracked"] == "155.83"  # tracked value does not change when it is billed
    assert usd_flow["invoiced"] == "127.50" and usd_flow["received"] == "100.00"
    balance = next(b for b in after["balances"] if b["currency"] == "USD")
    assert balance == {"currency": "USD", "unbilled": "28.33", "outstanding": "27.50", "overdue": "0.00"}
    assert after["invoices"] == {"draft": 0, "open": 1, "overdue": 0}
    assert [p["name"] for p in after["top_projects"]] == ["App", "Site"]
    assert after["top_projects"][0]["amounts"] == [{"currency": "USD", "amount": "155.83"}]


def test_overdue_balance_and_previous_period(client: TestClient, alice: AuthedUser, clock: FakeClock) -> None:
    c = make_client(client, alice, "Acme", currency="USD")
    p = make_project(client, alice, c["id"], "App", hourly_rate="100.00")
    entry_at(client, alice, p["id"], "2026-09-15T09:00:00+00:00", 60)
    e = entry_at(client, alice, p["id"], "2026-10-02T09:00:00+00:00", 30)
    inv = create_invoice(
        client, alice, c["id"], time_entry_ids=[e["id"]], issue_date="2026-10-02", due_date="2026-10-09"
    ).json()
    client.post(f"{API}/invoices/{inv['id']}/send", headers=alice.headers)

    summary = _get(client, alice, "/dashboard/summary", period="month")
    assert summary["previous_tracked_seconds"] == 3600
    assert _flow(summary, "USD")["previous_tracked"] == "100.00"
    balance = next(b for b in summary["balances"] if b["currency"] == "USD")
    assert balance["outstanding"] == balance["overdue"] == "50.00"
    assert summary["invoices"]["overdue"] == 1


def test_local_day_attribution_follows_the_user_time_zone(client: TestClient) -> None:
    """22:30 UTC on Oct 11 is already Oct 12 in Kyiv (UTC+3): the entry moves to the next day there."""
    results = {}
    for tz in ("UTC", "Europe/Kyiv"):
        user = register(client, f"{tz.replace('/', '-').lower()}@example.com", timezone=tz)
        c = make_client(client, user, "Acme")
        p = make_project(client, user, c["id"], "App", hourly_rate="60.00")
        entry_at(client, user, p["id"], "2026-10-11T22:30:00+00:00", 60)
        series = _get(client, user, "/analytics/timeseries", **{"from": "2026-10-11", "to": "2026-10-12"})
        results[tz] = {pt["start"]: pt["seconds"] for pt in series["points"]}
    assert results["UTC"] == {"2026-10-11": 3600, "2026-10-12": 0}
    assert results["Europe/Kyiv"] == {"2026-10-11": 0, "2026-10-12": 3600}

    kyiv = register(client, "kyiv-today@example.com", timezone="Europe/Kyiv")
    c = make_client(client, kyiv, "Acme")
    p = make_project(client, kyiv, c["id"], "App", hourly_rate="60.00")
    entry_at(client, kyiv, p["id"], "2026-10-11T22:30:00+00:00", 60)
    today = _get(client, kyiv, "/dashboard/summary", period="today")  # clock: 2026-10-12 13:00 Kyiv
    assert today["range"] == {"from": "2026-10-12", "to": "2026-10-12"} and today["tracked_seconds"] == 3600


def test_dst_day_buckets_and_week_start(client: TestClient, clock: FakeClock) -> None:
    """America/New_York leaves DST on 2026-11-01 (a 25-hour local day)."""
    clock.set(datetime(2026, 11, 10, 12, 0, tzinfo=UTC))
    user = register(client, "ny@example.com", timezone="America/New_York")
    c = make_client(client, user, "Acme")
    p = make_project(client, user, c["id"], "App", hourly_rate="60.00")
    entry_at(client, user, p["id"], "2026-11-01T04:30:00+00:00", 30)  # 00:30 EDT, Nov 1
    entry_at(client, user, p["id"], "2026-11-02T04:30:00+00:00", 30)  # 23:30 EST, still Nov 1
    entry_at(client, user, p["id"], "2026-11-02T05:30:00+00:00", 30)  # 00:30 EST, Nov 2

    days = _get(client, user, "/analytics/timeseries", **{"from": "2026-10-31", "to": "2026-11-02", "interval": "day"})
    assert [(pt["start"], pt["seconds"]) for pt in days["points"]] == [
        ("2026-10-31", 0),
        ("2026-11-01", 3600),
        ("2026-11-02", 1800),
    ]

    # Sunday Nov 1: with Monday weeks it closes the week of Oct 26; with Sunday weeks it opens a new one.
    monday = _get(
        client, user, "/analytics/timeseries", **{"from": "2026-10-26", "to": "2026-11-08", "interval": "week"}
    )
    assert [(pt["start"], pt["end"], pt["seconds"]) for pt in monday["points"]] == [
        ("2026-10-26", "2026-11-01", 3600),
        ("2026-11-02", "2026-11-08", 1800),
    ]
    client.patch(f"{API}/me", json={"week_start": 7}, headers=user.headers)
    sunday = _get(
        client, user, "/analytics/timeseries", **{"from": "2026-10-26", "to": "2026-11-08", "interval": "week"}
    )
    assert [(pt["start"], pt["end"], pt["seconds"]) for pt in sunday["points"]] == [
        ("2026-10-26", "2026-10-31", 0),  # clipped to the requested range
        ("2026-11-01", "2026-11-07", 5400),
        ("2026-11-08", "2026-11-08", 0),
    ]


def test_timeseries_money_and_auto_interval(client: TestClient, alice: AuthedUser) -> None:
    c = make_client(client, alice, "Acme", currency="USD")
    p = make_project(client, alice, c["id"], "App", hourly_rate="85.00")
    entry_at(client, alice, p["id"], "2026-10-05T09:00:00+00:00", 90)
    month = _get(client, alice, "/analytics/timeseries", period="month")
    assert month["interval"] == "day" and len(month["points"]) == 31
    point = next(pt for pt in month["points"] if pt["start"] == "2026-10-05")
    assert point["tracked"] == [{"currency": "USD", "amount": "127.50"}] and point["received"] == []
    year = _get(client, alice, "/analytics/timeseries", period="year")
    assert year["interval"] == "month" and len(year["points"]) == 12
    october = year["points"][9]
    assert october["start"] == "2026-10-01" and october["end"] == "2026-10-31" and october["seconds"] == 5400


def test_breakdown_by_project_and_client_with_effective_rates(client: TestClient, alice: AuthedUser) -> None:
    acme = make_client(client, alice, "Acme", currency="USD")
    hourly = make_project(client, alice, acme["id"], "App", hourly_rate="90.00")
    fixed = make_project(client, alice, acme["id"], "Logo", billing_type="fixed", fixed_fee="1000.00")
    entry_at(client, alice, hourly["id"], "2026-10-05T09:00:00+00:00", 40)  # 60.00
    entry_at(client, alice, hourly["id"], "2026-10-05T10:00:00+00:00", 20, billable=False)
    entry_at(client, alice, fixed["id"], "2026-09-20T09:00:00+00:00", 300)  # previous month, counts all-time
    entry_at(client, alice, fixed["id"], "2026-10-06T09:00:00+00:00", 180)

    body = _get(client, alice, "/analytics/breakdown", period="month", group_by="project")
    rows = {r["name"]: r for r in body["rows"]}
    assert body["total_seconds"] == (40 + 20 + 180) * 60
    assert [r["name"] for r in body["rows"]] == ["Logo", "App"]
    assert rows["App"]["amounts"] == [{"currency": "USD", "amount": "60.00"}]
    # Billable but unpriced time never dilutes the rate; non-billable time is not in the denominator.
    assert rows["App"]["effective_hourly_rate"] == [{"currency": "USD", "rate": "90.00"}]
    assert rows["App"]["billable_seconds"] == 2400
    assert rows["Logo"]["billing_type"] == "fixed" and rows["Logo"]["amounts"] == []
    assert rows["Logo"]["effective_hourly_rate"] == [{"currency": "USD", "rate": "125.00"}]  # 1000 / 8 h
    assert abs(rows["Logo"]["share"] - 0.75) < 1e-9

    by_client = _get(client, alice, "/analytics/breakdown", period="month", group_by="client")
    assert [(r["name"], r["seconds"]) for r in by_client["rows"]] == [("Acme", 240 * 60)]
    assert by_client["rows"][0]["effective_hourly_rate"] == [{"currency": "USD", "rate": "90.00"}]


def test_project_summary(client: TestClient, alice: AuthedUser) -> None:
    c = make_client(client, alice, "Acme", currency="USD", default_hourly_rate="70.00")
    p = make_project(client, alice, c["id"], "App", budget_hours="10.00")  # no own rate → client rate
    task = make_task(client, alice, p["id"], "Auth")
    e1 = entry_at(client, alice, p["id"], "2026-10-05T09:00:00+00:00", 120, task_id=task["id"])  # 140.00
    entry_at(client, alice, p["id"], "2026-08-01T09:00:00+00:00", 60)  # 70.00, older than 30 days
    inv = create_invoice(client, alice, c["id"], time_entry_ids=[e1["id"]]).json()
    client.post(f"{API}/invoices/{inv['id']}/send", headers=alice.headers)

    s = _get(client, alice, f"/projects/{p['id']}/summary")
    assert s["tracked_seconds"] == 3 * 3600 and s["entries"] == 2
    assert s["budget_used"] == 0.3 and s["budget_hours"] == "10.00"
    assert s["current_rate"] == {"rate": "70.00", "currency": "USD", "source": "client"}
    assert s["money"] == [{"currency": "USD", "tracked": "210.00", "unbilled": "70.00", "invoiced": "140.00"}]
    assert s["effective_hourly_rate"] == [{"currency": "USD", "rate": "70.00"}]
    assert [(t["title"], t["seconds"]) for t in s["by_task"]] == [("Auth", 7200), (None, 3600)]
    assert s["last_30_days_seconds"] == 7200
    assert s["first_entry_at"].startswith("2026-08-01") and s["last_entry_at"].startswith("2026-10-05")


def test_range_validation_and_ownership(client: TestClient, alice: AuthedUser, bob: AuthedUser) -> None:
    for path in ("/dashboard/summary", "/analytics/timeseries", "/analytics/breakdown"):
        bad = client.get(f"{API}{path}", params={"from": "2026-10-10", "to": "2026-10-01"}, headers=alice.headers)
        assert_problem(bad, 422, "VALIDATION_ERROR")
        long = client.get(f"{API}{path}", params={"from": "2025-01-01", "to": "2026-10-01"}, headers=alice.headers)
        assert_problem(long, 422, "VALIDATION_ERROR")
        assert client.get(f"{API}{path}").status_code == 401
    assert client.get(f"{API}/dashboard/summary", params={"period": "decade"}, headers=alice.headers).status_code == 422

    c = make_client(client, alice, "Acme")
    p = make_project(client, alice, c["id"], "App", hourly_rate="50.00")
    entry_at(client, alice, p["id"], "2026-10-05T09:00:00+00:00", 60)
    assert_problem(client.get(f"{API}/projects/{p['id']}/summary", headers=bob.headers), 404, "NOT_FOUND")
    bobs = _get(client, bob, "/dashboard/summary", period="month")
    assert bobs["tracked_seconds"] == 0 and bobs["flows"] == [] and bobs["balances"] == []
    assert bobs["top_projects"] == []
