from fastapi.testclient import TestClient

from tests.conftest import AuthedUser
from tests.helpers import assert_problem


def test_health(client: TestClient) -> None:
    assert client.get("/api/v1/health").json() == {"status": "ok"}
    assert client.get("/api/v1/health/ready").json() == {"status": "ok"}


def test_unknown_route_and_method_use_problem_details(client: TestClient, alice: AuthedUser) -> None:
    assert_problem(client.get("/api/v1/nope"), 404, "NOT_FOUND")
    assert_problem(client.put("/api/v1/me", headers=alice.headers, json={}), 405, "METHOD_NOT_ALLOWED")


def test_invalid_uuid_in_path(client: TestClient, alice: AuthedUser) -> None:
    body = assert_problem(client.get("/api/v1/clients/not-a-uuid", headers=alice.headers), 422, "VALIDATION_ERROR")
    assert body["errors"][0]["field"] == "client_id"


def test_malformed_json(client: TestClient, alice: AuthedUser) -> None:
    r = client.post("/api/v1/clients", headers={**alice.headers, "Content-Type": "application/json"}, content=b"{oops")
    assert_problem(r, 422, "VALIDATION_ERROR")


def test_request_id_is_echoed_or_generated(client: TestClient) -> None:
    assert client.get("/api/v1/health", headers={"X-Request-ID": "abc-123"}).headers["X-Request-ID"] == "abc-123"
    generated = client.get("/api/v1/health").headers["X-Request-ID"]
    assert len(generated) == 32
    body = client.get("/api/v1/nope", headers={"X-Request-ID": "trace-me"}).json()
    assert body["request_id"] == "trace-me" and body["type"].endswith("/not-found")


def test_unhandled_errors_do_not_leak_internals(app, client: TestClient) -> None:  # type: ignore[no-untyped-def]
    @app.get("/api/v1/_boom")
    def boom() -> None:
        raise RuntimeError("secret internal detail")

    with TestClient(app, raise_server_exceptions=False) as c:
        r = c.get("/api/v1/_boom")
    body = assert_problem(r, 500, "INTERNAL_ERROR")
    assert "secret" not in r.text
    assert body["request_id"] and r.headers["X-Request-ID"] == body["request_id"]


def test_openapi_is_versioned(client: TestClient) -> None:
    spec = client.get("/api/v1/openapi.json").json()
    assert all(path.startswith("/api/v1/") for path in spec["paths"])
    # Money fields are documented as strings, not numbers.
    rate = spec["components"]["schemas"]["ClientCreate"]["properties"]["default_hourly_rate"]
    assert '"string"' in str(rate).replace("'", '"')
