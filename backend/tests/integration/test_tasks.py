from fastapi.testclient import TestClient

from tests.conftest import AuthedUser
from tests.helpers import assert_problem, make_client, make_project, make_task

API = "/api/v1/tasks"


def _project(client: TestClient, user: AuthedUser) -> dict:  # type: ignore[type-arg]
    return make_project(client, user, make_client(client, user)["id"])


def test_create_assigns_increasing_positions(client: TestClient, alice: AuthedUser) -> None:
    p = _project(client, alice)
    positions = [make_task(client, alice, p["id"], f"T{i}")["position"] for i in range(3)]
    assert positions == [0, 1, 2]


def test_completed_at_follows_status(client: TestClient, alice: AuthedUser) -> None:
    p = _project(client, alice)
    t = make_task(client, alice, p["id"], estimate_minutes=90, priority="high", due_date="2026-11-01")
    assert t["completed_at"] is None and t["priority"] == "high"
    done = client.patch(f"{API}/{t['id']}", headers=alice.headers, json={"status": "done"}).json()
    assert done["completed_at"] is not None
    again = client.patch(f"{API}/{t['id']}", headers=alice.headers, json={"status": "done"}).json()
    assert again["completed_at"] == done["completed_at"]  # idempotent
    reopened = client.patch(f"{API}/{t['id']}", headers=alice.headers, json={"status": "in_progress"}).json()
    assert reopened["completed_at"] is None
    assert make_task(client, alice, p["id"], "born done", status="done")["completed_at"] is not None


def test_validation_and_immutable_project(client: TestClient, alice: AuthedUser) -> None:
    p = _project(client, alice)
    t = make_task(client, alice, p["id"])
    for payload in (
        {"project_id": p["id"], "title": ""},
        {"project_id": p["id"], "title": "x", "estimate_minutes": 0},
        {"project_id": p["id"], "title": "x", "priority": "urgent"},
    ):
        assert_problem(client.post(API, headers=alice.headers, json=payload), 422, "VALIDATION_ERROR")
    other = make_project(client, alice, make_client(client, alice, "B")["id"])
    assert_problem(
        client.patch(f"{API}/{t['id']}", headers=alice.headers, json={"project_id": other["id"]}),
        422,
        "VALIDATION_ERROR",
    )
    assert_problem(
        client.patch(f"{API}/{t['id']}", headers=alice.headers, json={"title": None}), 422, "VALIDATION_ERROR"
    )


def test_list_by_project_in_position_order_with_pagination(client: TestClient, alice: AuthedUser) -> None:
    p = _project(client, alice)
    ids = [make_task(client, alice, p["id"], f"T{i}")["id"] for i in range(5)]
    first = client.get(API, headers=alice.headers, params={"project_id": p["id"], "limit": 3}).json()
    rest = client.get(
        API, headers=alice.headers, params={"project_id": p["id"], "limit": 3, "cursor": first["next_cursor"]}
    ).json()
    assert [t["id"] for t in first["items"] + rest["items"]] == ids and rest["next_cursor"] is None


def test_list_across_projects_by_due_date(client: TestClient, alice: AuthedUser) -> None:
    p1, p2 = _project(client, alice), make_project(client, alice, make_client(client, alice, "B")["id"])
    make_task(client, alice, p1["id"], "later", due_date="2026-12-01")
    make_task(client, alice, p2["id"], "soon", due_date="2026-10-20")
    make_task(client, alice, p1["id"], "undated")
    make_task(client, alice, p2["id"], "done", due_date="2026-10-01", status="done")

    def titles(**params: object) -> list[str]:
        return [t["title"] for t in client.get(API, headers=alice.headers, params=params).json()["items"]]

    assert titles() == ["done", "soon", "later", "undated"]
    assert titles(status="todo") == ["soon", "later", "undated"]
    assert titles(due_before="2026-11-01") == ["done", "soon"]
    first = client.get(API, headers=alice.headers, params={"limit": 3}).json()
    rest = client.get(API, headers=alice.headers, params={"limit": 3, "cursor": first["next_cursor"]}).json()
    assert [t["title"] for t in rest["items"]] == ["undated"]


def test_reorder(client: TestClient, alice: AuthedUser) -> None:
    p = _project(client, alice)
    a, b, c = (make_task(client, alice, p["id"], n)["id"] for n in "abc")
    assert (
        client.post(
            f"{API}/reorder", headers=alice.headers, json={"project_id": p["id"], "ordered_ids": [c, a, b]}
        ).status_code
        == 204
    )
    listed = client.get(API, headers=alice.headers, params={"project_id": p["id"]}).json()["items"]
    assert [t["id"] for t in listed] == [c, a, b]
    for bad in ([a, b], [a, b, c, c], [a, b, c, "00000000-0000-4000-8000-000000000000"]):
        assert_problem(
            client.post(f"{API}/reorder", headers=alice.headers, json={"project_id": p["id"], "ordered_ids": bad}),
            422,
            "VALIDATION_ERROR",
        )


def test_delete(client: TestClient, alice: AuthedUser) -> None:
    t = make_task(client, alice, _project(client, alice)["id"])
    assert client.delete(f"{API}/{t['id']}", headers=alice.headers).status_code == 204
    assert_problem(client.delete(f"{API}/{t['id']}", headers=alice.headers), 404, "NOT_FOUND")


def test_unknown_project(client: TestClient, alice: AuthedUser) -> None:
    missing = "00000000-0000-4000-8000-000000000000"
    assert_problem(
        client.post(API, headers=alice.headers, json={"project_id": missing, "title": "x"}), 404, "NOT_FOUND"
    )
    assert_problem(client.get(API, headers=alice.headers, params={"project_id": missing}), 404, "NOT_FOUND")
