from fastapi.testclient import TestClient

from tests.conftest import AuthedUser
from tests.helpers import assert_problem, make_client, make_project, make_task

API = "/api/v1/projects"


def test_create_defaults_and_shape(client: TestClient, alice: AuthedUser) -> None:
    c = make_client(client, alice, "Acme", currency="EUR")
    p = make_project(
        client,
        alice,
        c["id"],
        "Mobile app",
        hourly_rate="80",
        budget_hours="120",
        deadline="2026-12-01",
        color="#4cc2ff",
    )
    assert p["client"] == {"id": c["id"], "name": "Acme"}
    assert p["currency"] == "EUR"  # inherited from client
    assert p["status"] == "active" and p["billing_type"] == "hourly"
    assert p["hourly_rate"] == "80.00" and p["budget_hours"] == "120.00" and p["color"] == "#4CC2FF"
    assert p["stats"] == {"tasks_total": 0, "tasks_done": 0, "tracked_seconds": 0, "unbilled": []}


def test_billing_rules(client: TestClient, alice: AuthedUser) -> None:
    c = make_client(client, alice)
    fixed = make_project(client, alice, c["id"], "Audit", billing_type="fixed", fixed_fee="2400")
    assert fixed["fixed_fee"] == "2400.00" and fixed["hourly_rate"] is None
    cases = [
        ({"billing_type": "fixed"}, "fixed_fee"),
        ({"billing_type": "fixed", "fixed_fee": "10", "hourly_rate": "5"}, "hourly_rate"),
        ({"billing_type": "hourly", "fixed_fee": "10"}, "fixed_fee"),
        ({"billing_type": "non_billable", "hourly_rate": "5"}, "hourly_rate"),
    ]
    for i, (payload, field) in enumerate(cases):
        r = client.post(API, headers=alice.headers, json={"client_id": c["id"], "name": f"P{i}", **payload})
        assert assert_problem(r, 422, "VALIDATION_ERROR")["errors"][0]["field"] == field


def test_switching_billing_type_clears_stale_values(client: TestClient, alice: AuthedUser) -> None:
    c = make_client(client, alice)
    p = make_project(client, alice, c["id"], hourly_rate="80")
    r = client.patch(f"{API}/{p['id']}", headers=alice.headers, json={"billing_type": "fixed", "fixed_fee": "1000"})
    assert r.status_code == 200, r.text
    assert r.json()["hourly_rate"] is None and r.json()["fixed_fee"] == "1000.00"
    r = client.patch(f"{API}/{p['id']}", headers=alice.headers, json={"billing_type": "non_billable"})
    assert r.json()["fixed_fee"] is None
    assert_problem(
        client.patch(f"{API}/{p['id']}", headers=alice.headers, json={"billing_type": "fixed"}), 422, "VALIDATION_ERROR"
    )


def test_unknown_or_archived_client(client: TestClient, alice: AuthedUser) -> None:
    missing = client.post(
        API, headers=alice.headers, json={"client_id": "00000000-0000-4000-8000-000000000000", "name": "X"}
    )
    assert_problem(missing, 404, "NOT_FOUND")
    c = make_client(client, alice)
    client.post(f"/api/v1/clients/{c['id']}/archive", headers=alice.headers)
    assert_problem(
        client.post(API, headers=alice.headers, json={"client_id": c["id"], "name": "X"}), 409, "CLIENT_ARCHIVED"
    )


def test_unique_name_per_client(client: TestClient, alice: AuthedUser) -> None:
    a, b = make_client(client, alice, "A"), make_client(client, alice, "B")
    make_project(client, alice, a["id"], "Site")
    make_project(client, alice, b["id"], "Site")  # same name under another client is fine
    assert_problem(
        client.post(API, headers=alice.headers, json={"client_id": a["id"], "name": "SITE"}), 409, "NAME_TAKEN"
    )


def test_move_to_other_client(client: TestClient, alice: AuthedUser) -> None:
    a, b = make_client(client, alice, "A"), make_client(client, alice, "B")
    p = make_project(client, alice, a["id"])
    r = client.patch(f"{API}/{p['id']}", headers=alice.headers, json={"client_id": b["id"]})
    assert r.json()["client"] == {"id": b["id"], "name": "B"}


def test_list_filters_and_pagination(client: TestClient, alice: AuthedUser) -> None:
    a, b = make_client(client, alice, "Alpha Co"), make_client(client, alice, "Beta Co")
    make_project(client, alice, a["id"], "API")
    make_project(client, alice, a["id"], "Web", status="completed")
    make_project(client, alice, b["id"], "Mobile")
    old = make_project(client, alice, b["id"], "Legacy")
    client.post(f"{API}/{old['id']}/archive", headers=alice.headers)

    def names(**params: object) -> list[str]:
        return [p["name"] for p in client.get(API, headers=alice.headers, params=params).json()["items"]]

    assert names() == ["API", "Mobile", "Web"]
    assert names(client_id=a["id"]) == ["API", "Web"]
    assert names(status="completed") == ["Web"]
    assert names(search="beta") == ["Mobile"]  # matches client name
    assert names(archived=True) == ["Legacy"]
    first = client.get(API, headers=alice.headers, params={"limit": 2}).json()
    rest = client.get(API, headers=alice.headers, params={"limit": 2, "cursor": first["next_cursor"]}).json()
    assert [p["name"] for p in first["items"] + rest["items"]] == ["API", "Mobile", "Web"]
    assert_problem(client.get(API, headers=alice.headers, params={"status": "nope"}), 422, "VALIDATION_ERROR")


def test_task_stats(client: TestClient, alice: AuthedUser) -> None:
    p = make_project(client, alice, make_client(client, alice)["id"])
    make_task(client, alice, p["id"], "a")
    make_task(client, alice, p["id"], "b", status="done")
    assert client.get(f"{API}/{p['id']}", headers=alice.headers).json()["stats"]["tasks_done"] == 1


def test_delete_cascades_tasks(client: TestClient, alice: AuthedUser) -> None:
    p = make_project(client, alice, make_client(client, alice)["id"])
    t = make_task(client, alice, p["id"])
    assert client.delete(f"{API}/{p['id']}", headers=alice.headers).status_code == 204
    assert_problem(client.get(f"/api/v1/tasks/{t['id']}", headers=alice.headers), 404, "NOT_FOUND")
