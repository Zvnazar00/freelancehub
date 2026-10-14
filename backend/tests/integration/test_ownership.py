"""Cross-user access matrix: every protected resource must be invisible to other users (404, never 403)."""

from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from tests.conftest import AuthedUser
from tests.helpers import assert_problem, make_client, make_project, make_task


@pytest.fixture
def alice_data(client: TestClient, alice: AuthedUser) -> dict[str, Any]:
    c = make_client(client, alice, "Alice Client")
    p = make_project(client, alice, c["id"], "Alice Project")
    t = make_task(client, alice, p["id"], "Alice Task")
    return {"client": c, "project": p, "task": t}


def _requests(d: dict[str, Any]) -> list[tuple[str, str, dict[str, Any] | None]]:
    c, p, t = d["client"]["id"], d["project"]["id"], d["task"]["id"]
    return [
        ("GET", f"/api/v1/clients/{c}", None),
        ("PATCH", f"/api/v1/clients/{c}", {"name": "hacked"}),
        ("POST", f"/api/v1/clients/{c}/archive", None),
        ("POST", f"/api/v1/clients/{c}/unarchive", None),
        ("DELETE", f"/api/v1/clients/{c}", None),
        ("GET", f"/api/v1/projects/{p}", None),
        ("PATCH", f"/api/v1/projects/{p}", {"name": "hacked"}),
        ("POST", f"/api/v1/projects/{p}/archive", None),
        ("POST", f"/api/v1/projects/{p}/unarchive", None),
        ("DELETE", f"/api/v1/projects/{p}", None),
        ("GET", f"/api/v1/tasks/{t}", None),
        ("PATCH", f"/api/v1/tasks/{t}", {"title": "hacked"}),
        ("DELETE", f"/api/v1/tasks/{t}", None),
        ("GET", f"/api/v1/tasks?project_id={p}", None),
        ("POST", "/api/v1/projects", {"client_id": c, "name": "Sneaky"}),
        ("POST", "/api/v1/tasks", {"project_id": p, "title": "Sneaky"}),
        ("POST", "/api/v1/tasks/reorder", {"project_id": p, "ordered_ids": [t]}),
    ]


def test_other_user_gets_404_everywhere(
    client: TestClient, alice: AuthedUser, bob: AuthedUser, alice_data: dict[str, Any]
) -> None:
    for method, url, body in _requests(alice_data):
        r = client.request(method, url, json=body, headers=bob.headers)
        assert_problem(r, 404, "NOT_FOUND"), f"{method} {url}"

    # Nothing changed for Alice.
    assert client.get(f"/api/v1/clients/{alice_data['client']['id']}", headers=alice.headers).json()["name"] == (
        "Alice Client"
    )
    assert client.get(f"/api/v1/tasks/{alice_data['task']['id']}", headers=alice.headers).json()["title"] == (
        "Alice Task"
    )


def test_other_users_projects_cannot_be_moved_into_or_out_of(
    client: TestClient, alice: AuthedUser, bob: AuthedUser, alice_data: dict[str, Any]
) -> None:
    bobs_project = make_project(client, bob, make_client(client, bob, "Bob Client")["id"])
    r = client.patch(
        f"/api/v1/projects/{bobs_project['id']}", headers=bob.headers, json={"client_id": alice_data["client"]["id"]}
    )
    assert_problem(r, 404, "NOT_FOUND")


def test_lists_never_include_other_users_data(
    client: TestClient, alice: AuthedUser, bob: AuthedUser, alice_data: dict[str, Any]
) -> None:
    for url in ("/api/v1/clients", "/api/v1/projects", "/api/v1/tasks"):
        assert client.get(url, headers=bob.headers).json()["items"] == []
    assert client.get("/api/v1/clients", headers=bob.headers, params={"search": "alice"}).json()["items"] == []


def test_client_supplied_user_id_is_rejected(client: TestClient, bob: AuthedUser, alice: AuthedUser) -> None:
    r = client.post("/api/v1/clients", headers=bob.headers, json={"name": "X", "user_id": alice.id})
    body = assert_problem(r, 422, "VALIDATION_ERROR")
    assert body["errors"][0]["field"] == "user_id"


def test_database_rejects_cross_user_links_even_if_the_app_had_a_bug(
    client: TestClient, alice: AuthedUser, bob: AuthedUser, alice_data: dict[str, Any], db: Session
) -> None:
    """Defence in depth: composite FKs (client_id, user_id) make cross-tenant rows impossible."""
    with pytest.raises(IntegrityError), db.begin_nested():
        db.execute(
            text(
                "INSERT INTO projects (id, user_id, client_id, name, currency) "
                "VALUES (gen_random_uuid(), :bob, :client, 'evil', 'USD')"
            ),
            {"bob": bob.id, "client": alice_data["client"]["id"]},
        )
    with pytest.raises(IntegrityError), db.begin_nested():
        db.execute(
            text(
                "INSERT INTO tasks (id, user_id, project_id, title) VALUES (gen_random_uuid(), :bob, :project, 'evil')"
            ),
            {"bob": bob.id, "project": alice_data["project"]["id"]},
        )
