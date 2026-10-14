from typing import Any

from fastapi.testclient import TestClient

from tests.conftest import AuthedUser


def make_client(client: TestClient, user: AuthedUser, name: str = "Acme", **extra: Any) -> dict[str, Any]:
    r = client.post("/api/v1/clients", json={"name": name, **extra}, headers=user.headers)
    assert r.status_code == 201, r.text
    return r.json()  # type: ignore[no-any-return]


def make_project(
    client: TestClient, user: AuthedUser, client_id: str, name: str = "App", **extra: Any
) -> dict[str, Any]:
    r = client.post("/api/v1/projects", json={"client_id": client_id, "name": name, **extra}, headers=user.headers)
    assert r.status_code == 201, r.text
    return r.json()  # type: ignore[no-any-return]


def make_task(
    client: TestClient, user: AuthedUser, project_id: str, title: str = "Task", **extra: Any
) -> dict[str, Any]:
    r = client.post("/api/v1/tasks", json={"project_id": project_id, "title": title, **extra}, headers=user.headers)
    assert r.status_code == 201, r.text
    return r.json()  # type: ignore[no-any-return]


def assert_problem(response: Any, status: int, code: str) -> dict[str, Any]:
    assert response.status_code == status, response.text
    assert response.headers["content-type"].startswith("application/problem+json")
    body: dict[str, Any] = response.json()
    assert body["code"] == code, body
    assert body["status"] == status
    return body


def new_key() -> str:
    import uuid

    return str(uuid.uuid4())


def timer_start(
    client: TestClient,
    user: AuthedUser,
    project_id: str,
    *,
    key: str | None = None,
    entry_id: str | None = None,
    **extra: Any,
) -> Any:
    import uuid

    body = {"id": entry_id or str(uuid.uuid4()), "project_id": project_id, **extra}
    return client.post("/api/v1/timer/start", json=body, headers={**user.headers, "Idempotency-Key": key or new_key()})


def timer_cmd(
    client: TestClient, user: AuthedUser, entry_id: str, command: str, *, key: str | None = None, **body: Any
) -> Any:
    return client.post(
        f"/api/v1/timer/{entry_id}/{command}", json=body, headers={**user.headers, "Idempotency-Key": key or new_key()}
    )


def manual_entry(
    client: TestClient,
    user: AuthedUser,
    project_id: str,
    started_at: str,
    ended_at: str,
    *,
    key: str | None = None,
    **extra: Any,
) -> Any:
    body = {"project_id": project_id, "started_at": started_at, "ended_at": ended_at, **extra}
    return client.post("/api/v1/time-entries", json=body, headers={**user.headers, "Idempotency-Key": key or new_key()})


def hourly_project(client: TestClient, user: AuthedUser, rate: str = "85.00", **extra: Any) -> dict[str, Any]:
    c = make_client(client, user, extra.pop("client_name", "Acme"), currency=extra.pop("currency", "USD"))
    return make_project(client, user, c["id"], extra.pop("name", "App"), hourly_rate=rate, **extra)


def entry_at(
    client: TestClient, user: AuthedUser, project_id: str, start: str, minutes: int, **extra: Any
) -> dict[str, Any]:
    """Manual entry starting at an ISO instant and lasting `minutes`."""
    from datetime import datetime, timedelta

    begin = datetime.fromisoformat(start)
    end = begin + timedelta(minutes=minutes)
    r = manual_entry(client, user, project_id, begin.isoformat(), end.isoformat(), **extra)
    assert r.status_code == 201, r.text
    return r.json()  # type: ignore[no-any-return]


def create_invoice(client: TestClient, user: AuthedUser, client_id: str, *, key: str | None = None, **body: Any) -> Any:
    return client.post(
        "/api/v1/invoices",
        json={"client_id": client_id, **body},
        headers={**user.headers, "Idempotency-Key": key or new_key()},
    )
