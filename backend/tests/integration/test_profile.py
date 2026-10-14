from fastapi.testclient import TestClient

from tests.conftest import AuthedUser
from tests.helpers import assert_problem

API = "/api/v1"


def test_get_me(client: TestClient, alice: AuthedUser) -> None:
    body = client.get(f"{API}/me", headers=alice.headers).json()
    assert body["id"] == alice.id and body["email"] == alice.email
    assert body["default_hourly_rate"] is None and body["week_start"] == 1


def test_update_profile(client: TestClient, alice: AuthedUser) -> None:
    r = client.patch(
        f"{API}/me",
        headers=alice.headers,
        json={
            "full_name": "Alice A.",
            "timezone": "Europe/Kyiv",
            "default_hourly_rate": "75.5",
            "default_currency": "UAH",
            "week_start": 7,
        },
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["default_hourly_rate"] == "75.50" and body["default_currency"] == "UAH" and body["week_start"] == 7
    assert (
        client.patch(f"{API}/me", headers=alice.headers, json={"default_hourly_rate": None}).json()[
            "default_hourly_rate"
        ]
        is None
    )


def test_update_profile_validation(client: TestClient, alice: AuthedUser) -> None:
    for payload in (
        {"timezone": "Nowhere/City"},
        {"week_start": 3},
        {"default_currency": "BTC"},
        {"default_hourly_rate": 75.5},
        {"full_name": None},
        {"email": "new@example.com"},
        {"id": alice.id},
    ):
        assert_problem(client.patch(f"{API}/me", headers=alice.headers, json=payload), 422, "VALIDATION_ERROR")


def test_change_password_keeps_current_session_and_revokes_others(client: TestClient, alice: AuthedUser) -> None:
    other = client.post(f"{API}/auth/login", json={"email": alice.email, "password": alice.password}).json()
    r = client.post(
        f"{API}/me/password",
        headers=alice.headers,
        json={"current_password": alice.password, "new_password": "brand-new-password"},
    )
    assert r.status_code == 204
    assert client.post(f"{API}/auth/refresh", json={"refresh_token": alice.refresh_token}).status_code == 200
    assert_problem(
        client.post(f"{API}/auth/refresh", json={"refresh_token": other["refresh_token"]}), 401, "TOKEN_INVALID"
    )
    assert_problem(
        client.post(f"{API}/auth/login", json={"email": alice.email, "password": alice.password}),
        401,
        "INVALID_CREDENTIALS",
    )
    assert (
        client.post(f"{API}/auth/login", json={"email": alice.email, "password": "brand-new-password"}).status_code
        == 200
    )


def test_change_password_errors(client: TestClient, alice: AuthedUser) -> None:
    body = assert_problem(
        client.post(
            f"{API}/me/password",
            headers=alice.headers,
            json={"current_password": "wrong-one", "new_password": "brand-new-password"},
        ),
        422,
        "VALIDATION_ERROR",
    )
    assert body["errors"][0]["field"] == "current_password"
    assert_problem(
        client.post(
            f"{API}/me/password",
            headers=alice.headers,
            json={"current_password": alice.password, "new_password": alice.password},
        ),
        422,
        "VALIDATION_ERROR",
    )


def test_legacy_time_zone_aliases_are_normalised(client: TestClient) -> None:
    """Browsers report CLDR ids such as Europe/Kiev; they are stored under the current IANA name."""
    r = client.post(
        "/api/v1/auth/register",
        json={
            "email": "kyiv@example.com",
            "password": "correct-horse-battery",
            "full_name": "K",
            "timezone": "Europe/Kiev",
        },
    )
    assert r.status_code == 201, r.text
    assert r.json()["user"]["timezone"] == "Europe/Kyiv"
    headers = {"Authorization": f"Bearer {r.json()['access_token']}"}
    r = client.patch("/api/v1/me", json={"timezone": "Asia/Calcutta"}, headers=headers)
    assert r.status_code == 200, r.text
    assert r.json()["timezone"] == "Asia/Kolkata"
    # History grouping uses the stored zone in SQL, so it must be one PostgreSQL knows.
    assert client.get("/api/v1/time-entries", headers=headers).status_code == 200
