"""Timer state machine over HTTP with a controllable clock."""

from typing import Any

from fastapi.testclient import TestClient

from tests.conftest import AuthedUser, FakeClock
from tests.helpers import (
    assert_problem,
    hourly_project,
    make_client,
    make_project,
    make_task,
    new_key,
    timer_cmd,
    timer_start,
)

API = "/api/v1/timer"


def started(client: TestClient, user: AuthedUser, project_id: str, **extra: Any) -> dict[str, Any]:
    r = timer_start(client, user, project_id, **extra)
    assert r.status_code == 201, r.text
    return r.json()["entry"]  # type: ignore[no-any-return]


class TestLifecycle:
    def test_start_pause_resume_stop_computes_net_duration_and_amount(
        self, client: TestClient, alice: AuthedUser, clock: FakeClock
    ) -> None:
        p = hourly_project(client, alice, "85.00")
        e = started(client, alice, p["id"], description="  Login form ")
        assert e["status"] == "running" and e["description"] == "Login form"
        assert e["started_at"] == "2026-10-12T10:00:00Z"
        assert e["hourly_rate"] == "85.00" and e["rate_source"] == "project" and e["billable"] is True

        clock.advance(minutes=60)
        paused = timer_cmd(client, alice, e["id"], "pause").json()["entry"]
        assert paused["status"] == "paused" and paused["elapsed_seconds"] == 3600

        clock.advance(minutes=30)  # paused time must not count
        assert client.get(f"{API}/current", headers=alice.headers).json()["entry"]["elapsed_seconds"] == 3600
        resumed = timer_cmd(client, alice, e["id"], "resume").json()["entry"]
        assert resumed["pauses"] == [{"paused_at": "2026-10-12T11:00:00Z", "resumed_at": "2026-10-12T11:30:00Z"}]

        clock.advance(minutes=30)
        stopped = timer_cmd(client, alice, e["id"], "stop").json()["entry"]
        assert stopped["status"] == "stopped"
        assert stopped["duration_seconds"] == 5400 and stopped["elapsed_seconds"] == 5400
        assert stopped["billable_amount"] == "127.50"
        assert stopped["ended_at"] == "2026-10-12T12:00:00Z"
        assert stopped["version"] == 4
        assert client.get(f"{API}/current", headers=alice.headers).json()["entry"] is None

    def test_stop_while_paused_closes_the_pause(self, client: TestClient, alice: AuthedUser, clock: FakeClock) -> None:
        e = started(client, alice, hourly_project(client, alice)["id"])
        clock.advance(minutes=20)
        timer_cmd(client, alice, e["id"], "pause")
        clock.advance(hours=3)
        stopped = timer_cmd(client, alice, e["id"], "stop", description="Done").json()["entry"]
        assert stopped["duration_seconds"] == 1200 and stopped["description"] == "Done"
        assert stopped["pauses"][0]["resumed_at"] == stopped["ended_at"]

    def test_multiple_pauses(self, client: TestClient, alice: AuthedUser, clock: FakeClock) -> None:
        e = started(client, alice, hourly_project(client, alice)["id"])
        for _ in range(3):
            clock.advance(minutes=10)
            timer_cmd(client, alice, e["id"], "pause")
            clock.advance(minutes=5)
            timer_cmd(client, alice, e["id"], "resume")
        clock.advance(minutes=10)
        stopped = timer_cmd(client, alice, e["id"], "stop").json()["entry"]
        assert stopped["duration_seconds"] == 40 * 60 and len(stopped["pauses"]) == 3

    def test_discard(self, client: TestClient, alice: AuthedUser) -> None:
        e = started(client, alice, hourly_project(client, alice)["id"])
        r = timer_cmd(client, alice, e["id"], "discard")
        assert r.status_code == 200 and r.json()["entry"] is None
        assert_problem(client.get(f"/api/v1/time-entries/{e['id']}", headers=alice.headers), 404, "NOT_FOUND")

    def test_current_reports_server_time(self, client: TestClient, alice: AuthedUser, clock: FakeClock) -> None:
        body = client.get(f"{API}/current", headers=alice.headers).json()
        assert body == {"entry": None, "server_time": "2026-10-12T10:00:00Z"}


class TestInvariants:
    def test_only_one_active_timer(self, client: TestClient, alice: AuthedUser) -> None:
        p = hourly_project(client, alice)
        first = started(client, alice, p["id"])
        body = assert_problem(timer_start(client, alice, p["id"]), 409, "ACTIVE_TIMER_EXISTS")
        assert body["context"]["active_entry"]["id"] == first["id"]
        timer_cmd(client, alice, first["id"], "pause")  # paused still counts as active
        assert_problem(timer_start(client, alice, p["id"]), 409, "ACTIVE_TIMER_EXISTS")

    def test_users_are_independent(self, client: TestClient, alice: AuthedUser, bob: AuthedUser) -> None:
        started(client, alice, hourly_project(client, alice)["id"])
        started(client, bob, hourly_project(client, bob)["id"])

    def test_invalid_transitions(self, client: TestClient, alice: AuthedUser, clock: FakeClock) -> None:
        e = started(client, alice, hourly_project(client, alice)["id"])
        assert_problem(timer_cmd(client, alice, e["id"], "resume"), 409, "INVALID_TRANSITION")
        clock.advance(minutes=1)
        timer_cmd(client, alice, e["id"], "pause")
        assert_problem(timer_cmd(client, alice, e["id"], "pause"), 409, "INVALID_TRANSITION")
        timer_cmd(client, alice, e["id"], "stop")
        for command in ("pause", "resume", "stop", "discard"):
            assert_problem(timer_cmd(client, alice, e["id"], command), 409, "INVALID_TRANSITION")

    def test_command_for_a_stale_entry_reports_mismatch(
        self, client: TestClient, alice: AuthedUser, clock: FakeClock
    ) -> None:
        p = hourly_project(client, alice)
        old = started(client, alice, p["id"])
        clock.advance(minutes=5)
        timer_cmd(client, alice, old["id"], "stop")
        clock.advance(minutes=1)
        new = started(client, alice, p["id"])
        body = assert_problem(timer_cmd(client, alice, old["id"], "stop"), 409, "TIMER_MISMATCH")
        assert body["context"]["active_entry"]["id"] == new["id"]  # a late "stop" never stops the wrong timer

    def test_other_users_entry_is_not_found(self, client: TestClient, alice: AuthedUser, bob: AuthedUser) -> None:
        e = started(client, alice, hourly_project(client, alice)["id"])
        for command in ("pause", "stop", "discard"):
            assert_problem(timer_cmd(client, bob, e["id"], command), 404, "NOT_FOUND")
        assert client.get(f"{API}/current", headers=bob.headers).json()["entry"] is None

    def test_other_users_project_or_task(self, client: TestClient, alice: AuthedUser, bob: AuthedUser) -> None:
        p = hourly_project(client, alice)
        assert_problem(timer_start(client, bob, p["id"]), 404, "NOT_FOUND")
        t = make_task(client, alice, p["id"])
        assert_problem(timer_start(client, bob, hourly_project(client, bob)["id"], task_id=t["id"]), 404, "NOT_FOUND")

    def test_task_must_belong_to_project(self, client: TestClient, alice: AuthedUser) -> None:
        p1 = hourly_project(client, alice)
        p2 = make_project(client, alice, make_client(client, alice, "Other")["id"], "Other app")
        t = make_task(client, alice, p2["id"])
        assert_problem(timer_start(client, alice, p1["id"], task_id=t["id"]), 422, "VALIDATION_ERROR")

    def test_archived_project_cannot_be_tracked(self, client: TestClient, alice: AuthedUser) -> None:
        p = hourly_project(client, alice)
        client.post(f"/api/v1/projects/{p['id']}/archive", headers=alice.headers)
        assert_problem(timer_start(client, alice, p["id"]), 409, "PROJECT_ARCHIVED")

    def test_idempotency_key_is_required(self, client: TestClient, alice: AuthedUser) -> None:
        p = hourly_project(client, alice)
        r = client.post(f"{API}/start", json={"id": new_key(), "project_id": p["id"]}, headers=alice.headers)
        assert_problem(r, 428, "IDEMPOTENCY_KEY_REQUIRED")


class TestRates:
    def test_snapshot_is_immutable_when_project_rate_changes(
        self, client: TestClient, alice: AuthedUser, clock: FakeClock
    ) -> None:
        p = hourly_project(client, alice, "100.00")
        e = started(client, alice, p["id"])
        client.patch(f"/api/v1/projects/{p['id']}", headers=alice.headers, json={"hourly_rate": "200.00"})
        clock.advance(hours=1)
        stopped = timer_cmd(client, alice, e["id"], "stop").json()["entry"]
        assert stopped["hourly_rate"] == "100.00" and stopped["billable_amount"] == "100.00"
        assert client.get(f"/api/v1/time-entries/{e['id']}", headers=alice.headers).json()["hourly_rate"] == "100.00"

    def test_rate_resolution_order(self, client: TestClient, alice: AuthedUser, clock: FakeClock) -> None:
        client.patch(
            "/api/v1/me", headers=alice.headers, json={"default_hourly_rate": "40.00", "default_currency": "PLN"}
        )
        c = make_client(client, alice, "With rate", default_hourly_rate="60.00", currency="EUR")
        no_rate_client = make_client(client, alice, "No rate", currency="USD")

        cases = [
            (make_project(client, alice, c["id"], "P1", hourly_rate="80.00"), ("80.00", "EUR", "project")),
            (make_project(client, alice, c["id"], "P2"), ("60.00", "EUR", "client")),
            (make_project(client, alice, no_rate_client["id"], "P3"), ("40.00", "PLN", "user")),
            (make_project(client, alice, c["id"], "P4", billing_type="fixed", fixed_fee="1000"), (None, "EUR", "none")),
        ]
        for project, (rate, currency, source) in cases:
            e = started(client, alice, project["id"])
            assert (e["hourly_rate"], e["currency"], e["rate_source"]) == (rate, currency, source)
            clock.advance(minutes=1)
            timer_cmd(client, alice, e["id"], "discard")

    def test_non_billable_entries_have_no_amount(self, client: TestClient, alice: AuthedUser, clock: FakeClock) -> None:
        p = hourly_project(client, alice)
        e = started(client, alice, p["id"], billable=False)
        clock.advance(hours=2)
        stopped = timer_cmd(client, alice, e["id"], "stop").json()["entry"]
        assert stopped["billable"] is False and stopped["billable_amount"] is None
        nb = make_project(
            client, alice, make_client(client, alice, "NB")["id"], "Internal", billing_type="non_billable"
        )
        e2 = started(client, alice, nb["id"])
        assert e2["billable"] is False and e2["hourly_rate"] is None


class TestClientTimestamps:
    def test_offline_at_is_used(self, client: TestClient, alice: AuthedUser, clock: FakeClock) -> None:
        e = started(client, alice, hourly_project(client, alice)["id"], at="2026-10-12T12:30:00+03:00")
        assert e["started_at"] == "2026-10-12T09:30:00Z"  # stored as UTC
        stopped = timer_cmd(client, alice, e["id"], "stop", at="2026-10-12T09:45:00Z").json()["entry"]
        assert stopped["duration_seconds"] == 900

    def test_future_skew_is_clamped_up_to_60s(self, client: TestClient, alice: AuthedUser) -> None:
        e = started(client, alice, hourly_project(client, alice)["id"], at="2026-10-12T10:00:45Z")
        assert e["started_at"] == "2026-10-12T10:00:00Z"

    def test_far_future_is_rejected(self, client: TestClient, alice: AuthedUser) -> None:
        r = timer_start(client, alice, hourly_project(client, alice)["id"], at="2026-10-12T10:05:00Z")
        assert_problem(r, 422, "TIMESTAMP_IN_FUTURE")

    def test_out_of_order_is_rejected(self, client: TestClient, alice: AuthedUser, clock: FakeClock) -> None:
        e = started(client, alice, hourly_project(client, alice)["id"])
        clock.advance(minutes=30)
        timer_cmd(client, alice, e["id"], "pause")
        r = timer_cmd(client, alice, e["id"], "resume", at="2026-10-12T10:10:00Z")
        assert_problem(r, 422, "TIMESTAMP_OUT_OF_ORDER")
        assert_problem(
            timer_cmd(client, alice, e["id"], "stop", at="2026-10-12T09:00:00Z"), 422, "TIMESTAMP_OUT_OF_ORDER"
        )

    def test_too_old_is_rejected(self, client: TestClient, alice: AuthedUser) -> None:
        r = timer_start(client, alice, hourly_project(client, alice)["id"], at="2026-10-01T10:00:00Z")
        assert_problem(r, 422, "TIMESTAMP_TOO_OLD")

    def test_naive_timestamps_are_rejected(self, client: TestClient, alice: AuthedUser) -> None:
        r = timer_start(client, alice, hourly_project(client, alice)["id"], at="2026-10-12T10:00:00")
        assert_problem(r, 422, "VALIDATION_ERROR")


class TestActiveEdits:
    def test_edit_running_entry(self, client: TestClient, alice: AuthedUser, clock: FakeClock) -> None:
        p = hourly_project(client, alice)
        t = make_task(client, alice, p["id"], "Login")
        e = started(client, alice, p["id"])
        r = client.patch(
            f"{API}/{e['id']}",
            headers=alice.headers,
            json={"description": "Forgot to start", "task_id": t["id"], "started_at": "2026-10-12T09:15:00Z"},
        )
        assert r.status_code == 200, r.text
        body = r.json()["entry"]
        assert body["task"] == {"id": t["id"], "title": "Login"} and body["started_at"] == "2026-10-12T09:15:00Z"
        assert body["elapsed_seconds"] == 45 * 60

    def test_cannot_move_start_after_first_pause(self, client: TestClient, alice: AuthedUser, clock: FakeClock) -> None:
        e = started(client, alice, hourly_project(client, alice)["id"])
        clock.advance(minutes=10)
        timer_cmd(client, alice, e["id"], "pause")
        clock.advance(minutes=10)
        r = client.patch(f"{API}/{e['id']}", headers=alice.headers, json={"started_at": "2026-10-12T10:15:00Z"})
        assert_problem(r, 422, "TIMESTAMP_OUT_OF_ORDER")
