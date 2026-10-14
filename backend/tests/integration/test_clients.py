from fastapi.testclient import TestClient

from tests.conftest import AuthedUser
from tests.helpers import assert_problem, make_client, make_project

API = "/api/v1/clients"


def test_create_and_get(client: TestClient, alice: AuthedUser) -> None:
    r = client.post(
        API,
        headers=alice.headers,
        json={
            "name": "  Northwind  ",
            "email": "PM@Northwind.io",
            "company": "Northwind Inc.",
            "default_hourly_rate": "85",
        },
    )
    assert r.status_code == 201
    created = r.json()
    assert created["name"] == "Northwind" and created["email"] == "pm@northwind.io"
    assert created["default_hourly_rate"] == "85.00"
    assert created["currency"] == "USD"  # user's default
    assert created["stats"] == {"active_projects": 0, "tracked_seconds": 0, "unbilled": []}
    assert client.get(f"{API}/{created['id']}", headers=alice.headers).json() == created


def test_currency_defaults_to_user_preference(client: TestClient, alice: AuthedUser) -> None:
    client.patch("/api/v1/me", headers=alice.headers, json={"default_currency": "EUR"})
    assert make_client(client, alice)["currency"] == "EUR"


def test_validation(client: TestClient, alice: AuthedUser) -> None:
    for payload in (
        {"name": ""},
        {"name": "x" * 121},
        {"name": "A", "currency": "XYZ"},
        {"name": "A", "default_hourly_rate": 10.5},
        {"name": "A", "email": "nope"},
        {"name": "A", "user_id": alice.id},
    ):
        assert_problem(client.post(API, headers=alice.headers, json=payload), 422, "VALIDATION_ERROR")


def test_unique_active_name_case_insensitive(client: TestClient, alice: AuthedUser) -> None:
    first = make_client(client, alice, "Acme")
    assert_problem(client.post(API, headers=alice.headers, json={"name": "ACME"}), 409, "NAME_TAKEN")
    client.post(f"{API}/{first['id']}/archive", headers=alice.headers)
    second = make_client(client, alice, "acme")  # archived names are free again
    assert_problem(client.post(f"{API}/{first['id']}/unarchive", headers=alice.headers), 409, "NAME_TAKEN")
    assert second["name"] == "acme"


def test_rename_conflict(client: TestClient, alice: AuthedUser) -> None:
    make_client(client, alice, "Acme")
    beta = make_client(client, alice, "Beta")
    assert_problem(client.patch(f"{API}/{beta['id']}", headers=alice.headers, json={"name": "acme"}), 409, "NAME_TAKEN")
    assert client.patch(f"{API}/{beta['id']}", headers=alice.headers, json={"name": "Beta"}).status_code == 200


def test_same_name_allowed_for_different_users(client: TestClient, alice: AuthedUser, bob: AuthedUser) -> None:
    make_client(client, alice, "Acme")
    make_client(client, bob, "Acme")


def test_update_partial_and_clear_fields(client: TestClient, alice: AuthedUser) -> None:
    c = make_client(client, alice, "Acme", email="a@acme.io", default_hourly_rate="50.00")
    r = client.patch(f"{API}/{c['id']}", headers=alice.headers, json={"email": None, "notes": "VIP"})
    body = r.json()
    assert body["email"] is None and body["notes"] == "VIP" and body["default_hourly_rate"] == "50.00"
    assert_problem(
        client.patch(f"{API}/{c['id']}", headers=alice.headers, json={"name": None}), 422, "VALIDATION_ERROR"
    )


def test_list_search_archive_filter_and_pagination(client: TestClient, alice: AuthedUser) -> None:
    for name in ["delta", "Alpha", "charlie", "Bravo", "echo"]:
        make_client(client, alice, name)
    archived = make_client(client, alice, "Zulu")
    client.post(f"{API}/{archived['id']}/archive", headers=alice.headers)

    page1 = client.get(API, headers=alice.headers, params={"limit": 2}).json()
    assert [c["name"] for c in page1["items"]] == ["Alpha", "Bravo"]
    page2 = client.get(API, headers=alice.headers, params={"limit": 2, "cursor": page1["next_cursor"]}).json()
    page3 = client.get(API, headers=alice.headers, params={"limit": 2, "cursor": page2["next_cursor"]}).json()
    assert [c["name"] for c in page2["items"] + page3["items"]] == ["charlie", "delta", "echo"]
    assert page3["next_cursor"] is None

    assert [c["name"] for c in client.get(API, headers=alice.headers, params={"search": "ha"}).json()["items"]] == [
        "Alpha",
        "charlie",
    ]
    assert [c["name"] for c in client.get(API, headers=alice.headers, params={"archived": True}).json()["items"]] == [
        "Zulu"
    ]
    # LIKE wildcards in the search term are treated literally.
    assert client.get(API, headers=alice.headers, params={"search": "%"}).json()["items"] == []


def test_bad_cursor_and_limits(client: TestClient, alice: AuthedUser) -> None:
    assert_problem(client.get(API, headers=alice.headers, params={"cursor": "garbage!"}), 400, "BAD_REQUEST")
    assert_problem(client.get(API, headers=alice.headers, params={"limit": 101}), 422, "VALIDATION_ERROR")


def test_active_projects_stat(client: TestClient, alice: AuthedUser) -> None:
    c = make_client(client, alice)
    make_project(client, alice, c["id"], "One")
    make_project(client, alice, c["id"], "Two", status="on_hold")
    assert client.get(f"{API}/{c['id']}", headers=alice.headers).json()["stats"]["active_projects"] == 1


def test_delete(client: TestClient, alice: AuthedUser) -> None:
    empty = make_client(client, alice, "Empty")
    assert client.delete(f"{API}/{empty['id']}", headers=alice.headers).status_code == 204
    assert_problem(client.get(f"{API}/{empty['id']}", headers=alice.headers), 404, "NOT_FOUND")

    busy = make_client(client, alice, "Busy")
    make_project(client, alice, busy["id"])
    assert_problem(client.delete(f"{API}/{busy['id']}", headers=alice.headers), 409, "RESOURCE_IN_USE")
