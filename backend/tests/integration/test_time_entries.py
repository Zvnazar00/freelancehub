"""Manual entries, edits with optimistic locking, delete rules, history and project/task interplay."""

from typing import Any

from fastapi.testclient import TestClient

from tests.conftest import AuthedUser, FakeClock
from tests.helpers import (
    assert_problem,
    hourly_project,
    make_client,
    make_project,
    make_task,
    manual_entry,
    timer_cmd,
    timer_start,
)

API = "/api/v1/time-entries"


def created(r: Any) -> dict[str, Any]:
    assert r.status_code == 201, r.text
    return r.json()  # type: ignore[no-any-return]


class TestManual:
    def test_create(self, client: TestClient, alice: AuthedUser) -> None:
        p = hourly_project(client, alice, "72.00", currency="EUR")
        e = created(
            manual_entry(client, alice, p["id"], "2026-10-11T08:00:00Z", "2026-10-11T09:30:00Z", description="Call")
        )
        assert e["source"] == "manual" and e["status"] == "stopped"
        assert e["duration_seconds"] == 5400 and e["billable_amount"] == "108.00" and e["currency"] == "EUR"
        assert e["pauses"] == [] and e["version"] == 1

    def test_validation(self, client: TestClient, alice: AuthedUser) -> None:
        p = hourly_project(client, alice)
        assert_problem(
            manual_entry(client, alice, p["id"], "2026-10-11T09:00:00Z", "2026-10-11T09:00:00Z"),
            422,
            "VALIDATION_ERROR",
        )
        assert_problem(
            manual_entry(client, alice, p["id"], "2026-10-12T09:00:00Z", "2026-10-12T11:00:00Z"),
            422,
            "TIMESTAMP_IN_FUTURE",
        )  # clock is 10:00Z
        body = assert_problem(
            manual_entry(client, alice, p["id"], "2026-10-10T08:00:00Z", "2026-10-11T08:00:01Z"),
            422,
            "VALIDATION_ERROR",
        )
        assert body["errors"][0]["code"] == "duration_too_long"

    def test_exactly_24h_is_allowed(self, client: TestClient, alice: AuthedUser) -> None:
        p = hourly_project(client, alice)
        e = created(manual_entry(client, alice, p["id"], "2026-10-10T08:00:00Z", "2026-10-11T08:00:00Z"))
        assert e["duration_seconds"] == 86_400

    def test_overlaps_are_rejected_with_the_conflicting_entry(self, client: TestClient, alice: AuthedUser) -> None:
        p = hourly_project(client, alice)
        first = created(manual_entry(client, alice, p["id"], "2026-10-11T08:00:00Z", "2026-10-11T09:00:00Z"))
        body = assert_problem(
            manual_entry(client, alice, p["id"], "2026-10-11T08:30:00Z", "2026-10-11T10:00:00Z"), 409, "TIME_OVERLAP"
        )
        assert body["context"]["conflicting_entry"]["id"] == first["id"]
        # Touching ranges [08:00, 09:00) and [09:00, 10:00) do not overlap.
        created(manual_entry(client, alice, p["id"], "2026-10-11T09:00:00Z", "2026-10-11T10:00:00Z"))

    def test_running_timer_blocks_entries_after_its_start(
        self, client: TestClient, alice: AuthedUser, clock: FakeClock
    ) -> None:
        p = hourly_project(client, alice)
        timer_start(client, alice, p["id"], at="2026-10-12T09:00:00Z")
        assert_problem(
            manual_entry(client, alice, p["id"], "2026-10-12T09:10:00Z", "2026-10-12T09:20:00Z"), 409, "TIME_OVERLAP"
        )
        created(manual_entry(client, alice, p["id"], "2026-10-12T08:00:00Z", "2026-10-12T09:00:00Z"))

    def test_starting_a_timer_inside_an_existing_entry_is_rejected(self, client: TestClient, alice: AuthedUser) -> None:
        p = hourly_project(client, alice)
        created(manual_entry(client, alice, p["id"], "2026-10-12T09:00:00Z", "2026-10-12T10:00:30Z"))
        assert_problem(timer_start(client, alice, p["id"]), 409, "TIME_OVERLAP")


class TestEdit:
    def _entry(self, client: TestClient, user: AuthedUser, **extra: Any) -> dict[str, Any]:
        p = hourly_project(client, user, "60.00")
        return created(manual_entry(client, user, p["id"], "2026-10-11T08:00:00Z", "2026-10-11T09:00:00Z", **extra))

    def test_edit_times_recomputes_with_the_same_snapshot(self, client: TestClient, alice: AuthedUser) -> None:
        e = self._entry(client, alice)
        client.patch(f"/api/v1/projects/{e['project']['id']}", headers=alice.headers, json={"hourly_rate": "999.00"})
        r = client.patch(
            f"{API}/{e['id']}",
            headers=alice.headers,
            json={"version": 1, "ended_at": "2026-10-11T09:30:00Z", "description": "Longer"},
        )
        body = r.json()
        assert r.status_code == 200, r.text
        assert body["duration_seconds"] == 5400 and body["billable_amount"] == "90.00"
        assert body["hourly_rate"] == "60.00" and body["version"] == 2 and body["rate_corrected_at"] is None

    def test_reprice_is_an_explicit_correction(self, client: TestClient, alice: AuthedUser, clock: FakeClock) -> None:
        e = self._entry(client, alice)
        client.patch(f"/api/v1/projects/{e['project']['id']}", headers=alice.headers, json={"hourly_rate": "90.00"})
        body = client.patch(f"{API}/{e['id']}", headers=alice.headers, json={"version": 1, "reprice": True}).json()
        assert body["hourly_rate"] == "90.00" and body["billable_amount"] == "90.00"
        assert body["rate_corrected_at"] == "2026-10-12T10:00:00Z"

    def test_optimistic_locking(self, client: TestClient, alice: AuthedUser) -> None:
        e = self._entry(client, alice)
        client.patch(f"{API}/{e['id']}", headers=alice.headers, json={"version": 1, "description": "A"})
        body = assert_problem(
            client.patch(f"{API}/{e['id']}", headers=alice.headers, json={"version": 1, "description": "B"}),
            409,
            "VERSION_CONFLICT",
        )
        assert body["context"]["current"]["description"] == "A" and body["context"]["current"]["version"] == 2

    def test_billable_toggle(self, client: TestClient, alice: AuthedUser) -> None:
        e = self._entry(client, alice)
        off = client.patch(f"{API}/{e['id']}", headers=alice.headers, json={"version": 1, "billable": False}).json()
        assert off["billable_amount"] is None
        on = client.patch(f"{API}/{e['id']}", headers=alice.headers, json={"version": 2, "billable": True}).json()
        assert on["billable_amount"] == "60.00"

    def test_editing_times_clips_pauses(self, client: TestClient, alice: AuthedUser, clock: FakeClock) -> None:
        p = hourly_project(client, alice, "60.00")
        clock.set(clock.now.replace(hour=8))
        e = timer_start(client, alice, p["id"]).json()["entry"]
        clock.advance(minutes=10)
        timer_cmd(client, alice, e["id"], "pause")  # 08:10-08:20
        clock.advance(minutes=10)
        timer_cmd(client, alice, e["id"], "resume")
        clock.advance(minutes=20)
        timer_cmd(client, alice, e["id"], "pause")  # 08:40-08:50
        clock.advance(minutes=10)
        timer_cmd(client, alice, e["id"], "resume")
        clock.advance(minutes=10)
        stopped = timer_cmd(client, alice, e["id"], "stop").json()["entry"]
        assert stopped["duration_seconds"] == 40 * 60
        body = client.patch(
            f"{API}/{e['id']}",
            headers=alice.headers,
            json={"version": stopped["version"], "ended_at": "2026-10-12T08:45:00Z"},
        ).json()
        assert body["pauses"] == [
            {"paused_at": "2026-10-12T08:10:00Z", "resumed_at": "2026-10-12T08:20:00Z"},
            {"paused_at": "2026-10-12T08:40:00Z", "resumed_at": "2026-10-12T08:45:00Z"},
        ]
        assert body["duration_seconds"] == 30 * 60 and body["billable_amount"] == "30.00"

    def test_edit_cannot_create_overlap_or_break_limits(self, client: TestClient, alice: AuthedUser) -> None:
        p = hourly_project(client, alice)
        a = created(manual_entry(client, alice, p["id"], "2026-10-11T08:00:00Z", "2026-10-11T09:00:00Z"))
        created(manual_entry(client, alice, p["id"], "2026-10-11T10:00:00Z", "2026-10-11T11:00:00Z"))
        assert_problem(
            client.patch(
                f"{API}/{a['id']}", headers=alice.headers, json={"version": 1, "ended_at": "2026-10-11T10:30:00Z"}
            ),
            409,
            "TIME_OVERLAP",
        )
        assert_problem(
            client.patch(
                f"{API}/{a['id']}", headers=alice.headers, json={"version": 1, "started_at": "2026-10-10T07:00:00Z"}
            ),
            422,
            "VALIDATION_ERROR",
        )
        assert_problem(
            client.patch(
                f"{API}/{a['id']}", headers=alice.headers, json={"version": 1, "ended_at": "2026-10-11T07:00:00Z"}
            ),
            422,
            "VALIDATION_ERROR",
        )

    def test_move_to_other_project_keeps_snapshot_and_drops_foreign_task(
        self, client: TestClient, alice: AuthedUser
    ) -> None:
        p1 = hourly_project(client, alice, "60.00")
        t1 = make_task(client, alice, p1["id"])
        e = created(
            manual_entry(client, alice, p1["id"], "2026-10-11T08:00:00Z", "2026-10-11T09:00:00Z", task_id=t1["id"])
        )
        p2 = make_project(client, alice, make_client(client, alice, "B")["id"], "B app", hourly_rate="10.00")
        body = client.patch(
            f"{API}/{e['id']}", headers=alice.headers, json={"version": 1, "project_id": p2["id"]}
        ).json()
        assert body["project"]["id"] == p2["id"] and body["task"] is None and body["hourly_rate"] == "60.00"
        t2 = make_task(client, alice, p2["id"])
        assert_problem(
            client.patch(f"{API}/{e['id']}", headers=alice.headers, json={"version": 2, "task_id": t1["id"]}),
            422,
            "VALIDATION_ERROR",
        )
        assert (
            client.patch(f"{API}/{e['id']}", headers=alice.headers, json={"version": 2, "task_id": t2["id"]}).json()[
                "task"
            ]["id"]
            == t2["id"]
        )

    def test_active_entries_are_edited_through_the_timer(self, client: TestClient, alice: AuthedUser) -> None:
        e = timer_start(client, alice, hourly_project(client, alice)["id"]).json()["entry"]
        assert_problem(
            client.patch(f"{API}/{e['id']}", headers=alice.headers, json={"version": 1}), 409, "INVALID_TRANSITION"
        )
        assert_problem(client.delete(f"{API}/{e['id']}", headers=alice.headers), 409, "INVALID_TRANSITION")


class TestDeleteAndRelations:
    def test_delete(self, client: TestClient, alice: AuthedUser, bob: AuthedUser) -> None:
        p = hourly_project(client, alice)
        e = created(manual_entry(client, alice, p["id"], "2026-10-11T08:00:00Z", "2026-10-11T09:00:00Z"))
        assert_problem(client.delete(f"{API}/{e['id']}", headers=bob.headers), 404, "NOT_FOUND")
        assert client.delete(f"{API}/{e['id']}", headers=alice.headers).status_code == 204
        assert_problem(client.get(f"{API}/{e['id']}", headers=alice.headers), 404, "NOT_FOUND")

    def test_project_with_time_cannot_be_deleted(self, client: TestClient, alice: AuthedUser) -> None:
        p = hourly_project(client, alice)
        created(manual_entry(client, alice, p["id"], "2026-10-11T08:00:00Z", "2026-10-11T09:00:00Z"))
        assert_problem(client.delete(f"/api/v1/projects/{p['id']}", headers=alice.headers), 409, "RESOURCE_IN_USE")

    def test_deleting_a_task_keeps_the_entry(self, client: TestClient, alice: AuthedUser) -> None:
        p = hourly_project(client, alice)
        t = make_task(client, alice, p["id"])
        e = created(
            manual_entry(client, alice, p["id"], "2026-10-11T08:00:00Z", "2026-10-11T09:00:00Z", task_id=t["id"])
        )
        client.delete(f"/api/v1/tasks/{t['id']}", headers=alice.headers)
        kept = client.get(f"{API}/{e['id']}", headers=alice.headers).json()
        assert kept["task"] is None and kept["duration_seconds"] == 3600


class TestHistory:
    def test_pagination_filters_and_summary(self, client: TestClient, alice: AuthedUser, bob: AuthedUser) -> None:
        usd = hourly_project(client, alice, "100.00")
        eur = hourly_project(client, alice, "50.00", client_name="Euro", currency="EUR", name="Euro app")
        for day in (5, 6, 7):
            created(
                manual_entry(client, alice, usd["id"], f"2026-10-{day:02d}T08:00:00Z", f"2026-10-{day:02d}T09:00:00Z")
            )
        created(manual_entry(client, alice, eur["id"], "2026-10-07T10:00:00Z", "2026-10-07T10:30:00Z"))
        created(manual_entry(client, alice, eur["id"], "2026-10-07T11:00:00Z", "2026-10-07T11:30:00Z", billable=False))
        hourly_project(client, bob)  # other users never leak in

        first = client.get(API, headers=alice.headers, params={"limit": 2}).json()
        rest = client.get(API, headers=alice.headers, params={"limit": 10, "cursor": first["next_cursor"]}).json()
        starts = [e["started_at"] for e in first["items"] + rest["items"]]
        assert starts == sorted(starts, reverse=True) and len(starts) == 5 and rest["next_cursor"] is None
        assert {s["currency"]: s for s in first["summary"]} == {
            "EUR": {"currency": "EUR", "seconds": 3600, "billable_seconds": 1800, "amount": "25.00"},
            "USD": {"currency": "USD", "seconds": 10800, "billable_seconds": 10800, "amount": "300.00"},
        }
        only_eur = client.get(API, headers=alice.headers, params={"project_id": eur["id"], "billable": True}).json()
        assert len(only_eur["items"]) == 1
        assert (
            client.get(API, headers=alice.headers, params={"client_id": usd["client"]["id"]}).json()["summary"][0][
                "seconds"
            ]
            == 10800
        )

    def test_range_validation(self, client: TestClient, alice: AuthedUser) -> None:
        assert_problem(
            client.get(API, headers=alice.headers, params={"from": "2026-10-10", "to": "2026-10-01"}),
            422,
            "VALIDATION_ERROR",
        )
        assert_problem(
            client.get(API, headers=alice.headers, params={"from": "2025-01-01", "to": "2026-10-01"}),
            422,
            "VALIDATION_ERROR",
        )
        assert_problem(client.get(API, headers=alice.headers, params={"cursor": "bad!"}), 400, "BAD_REQUEST")
