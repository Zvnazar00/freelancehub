"""Tracked time and unbilled amounts embedded in project/client responses (docs/api.md §4.3, §4.4)."""

from fastapi.testclient import TestClient

from tests.conftest import AuthedUser
from tests.helpers import hourly_project, make_project, manual_entry, timer_start


def _stats(client: TestClient, user: AuthedUser, path: str) -> dict:  # type: ignore[type-arg]
    r = client.get(path, headers=user.headers)
    assert r.status_code == 200, r.text
    return r.json()["stats"]  # type: ignore[no-any-return]


def test_new_project_and_client_have_zero_stats(client: TestClient, alice: AuthedUser) -> None:
    project = hourly_project(client, alice)
    assert project["stats"]["tracked_seconds"] == 0
    assert project["stats"]["unbilled"] == []
    stats = _stats(client, alice, f"/api/v1/clients/{project['client']['id']}")
    assert stats == {"active_projects": 1, "tracked_seconds": 0, "unbilled": []}


def test_stats_sum_stopped_entries_per_currency(client: TestClient, alice: AuthedUser) -> None:
    project = hourly_project(client, alice, rate="100.00")  # USD
    client_id = project["client"]["id"]
    eur = make_project(client, alice, client_id, "Euro work", hourly_rate="60.00", currency="EUR")
    free = make_project(client, alice, client_id, "Internal", billing_type="non_billable")

    # 90 min @ 100 USD = 150.00; 30 min @ 60 EUR = 30.00; 1 h non-billable = no amount.
    assert manual_entry(client, alice, project["id"], "2026-10-12T06:00:00Z", "2026-10-12T07:30:00Z").status_code == 201
    assert manual_entry(client, alice, eur["id"], "2026-10-12T08:00:00Z", "2026-10-12T08:30:00Z").status_code == 201
    assert manual_entry(client, alice, free["id"], "2026-10-11T08:00:00Z", "2026-10-11T09:00:00Z").status_code == 201

    p = _stats(client, alice, f"/api/v1/projects/{project['id']}")
    assert p["tracked_seconds"] == 5400
    assert p["unbilled"] == [{"currency": "USD", "amount": "150.00"}]

    f = _stats(client, alice, f"/api/v1/projects/{free['id']}")
    assert f["tracked_seconds"] == 3600
    assert f["unbilled"] == []

    c = _stats(client, alice, f"/api/v1/clients/{client_id}")
    assert c["tracked_seconds"] == 5400 + 1800 + 3600
    assert c["unbilled"] == [
        {"currency": "USD", "amount": "150.00"},
        {"currency": "EUR", "amount": "30.00"},
    ]

    listed = client.get("/api/v1/projects", headers=alice.headers).json()["items"]
    by_id = {item["id"]: item["stats"] for item in listed}
    assert by_id[eur["id"]]["unbilled"] == [{"currency": "EUR", "amount": "30.00"}]
    listed_clients = client.get("/api/v1/clients", headers=alice.headers).json()["items"]
    assert listed_clients[0]["stats"]["tracked_seconds"] == 10800


def test_active_timer_is_not_counted(client: TestClient, alice: AuthedUser) -> None:
    project = hourly_project(client, alice)
    assert timer_start(client, alice, project["id"]).status_code == 201
    stats = _stats(client, alice, f"/api/v1/projects/{project['id']}")
    assert stats["tracked_seconds"] == 0
    assert stats["unbilled"] == []


def test_stats_never_include_other_users_entries(client: TestClient, alice: AuthedUser, bob: AuthedUser) -> None:
    a = hourly_project(client, alice)
    b = hourly_project(client, bob)
    assert manual_entry(client, bob, b["id"], "2026-10-12T06:00:00Z", "2026-10-12T08:00:00Z").status_code == 201
    assert _stats(client, alice, f"/api/v1/projects/{a['id']}")["tracked_seconds"] == 0
    assert _stats(client, bob, f"/api/v1/projects/{b['id']}")["tracked_seconds"] == 7200
