"""Retries and duplicate requests (single-threaded). Concurrent duplicates are in test_timer_concurrency.py."""

import uuid

from fastapi.testclient import TestClient
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models import IdempotencyKey, TimeEntry
from tests.conftest import AuthedUser, FakeClock
from tests.helpers import assert_problem, hourly_project, manual_entry, timer_cmd, timer_start


def count_entries(db: Session) -> int:
    return db.scalar(select(func.count()).select_from(TimeEntry)) or 0


def test_replayed_start_returns_the_original_response(
    client: TestClient, alice: AuthedUser, db: Session, clock: FakeClock
) -> None:
    p = hourly_project(client, alice)
    key, entry_id = str(uuid.uuid4()), str(uuid.uuid4())
    first = timer_start(client, alice, p["id"], key=key, entry_id=entry_id)
    clock.advance(minutes=5)
    replay = timer_start(client, alice, p["id"], key=key, entry_id=entry_id)
    assert first.status_code == replay.status_code == 201
    assert replay.json() == first.json()  # byte-for-byte, including the original server_time
    assert replay.headers["Idempotent-Replayed"] == "true" and "Idempotent-Replayed" not in first.headers
    assert count_entries(db) == 1


def test_replayed_stop_does_not_stop_twice(client: TestClient, alice: AuthedUser, clock: FakeClock) -> None:
    p = hourly_project(client, alice)
    e = timer_start(client, alice, p["id"]).json()["entry"]
    clock.advance(minutes=30)
    key = str(uuid.uuid4())
    first = timer_cmd(client, alice, e["id"], "stop", key=key)
    clock.advance(minutes=30)
    replay = timer_cmd(client, alice, e["id"], "stop", key=key)
    assert replay.status_code == 200 and replay.json() == first.json()
    assert replay.json()["entry"]["duration_seconds"] == 1800


def test_late_retry_of_pause_cannot_pause_again(client: TestClient, alice: AuthedUser, clock: FakeClock) -> None:
    """pause(K1) → resume(K2) → retry of pause(K1) arrives late: must replay, not pause a second time."""
    e = timer_start(client, alice, hourly_project(client, alice)["id"]).json()["entry"]
    clock.advance(minutes=10)
    timer_cmd(client, alice, e["id"], "pause", key="pause-key-1")
    clock.advance(minutes=5)
    timer_cmd(client, alice, e["id"], "resume", key="resume-key-1")
    clock.advance(minutes=5)
    late = timer_cmd(client, alice, e["id"], "pause", key="pause-key-1")
    assert late.status_code == 200 and late.json()["entry"]["status"] == "paused"  # the original answer
    current = client.get("/api/v1/timer/current", headers=alice.headers).json()["entry"]
    assert current["status"] == "running" and len(current["pauses"]) == 1


def test_same_entry_id_with_a_new_key_returns_the_existing_entry(
    client: TestClient, alice: AuthedUser, db: Session
) -> None:
    """An offline client that lost its key still cannot create a duplicate: the entry ID is the second guard."""
    p = hourly_project(client, alice)
    entry_id = str(uuid.uuid4())
    first = timer_start(client, alice, p["id"], entry_id=entry_id)
    again = timer_start(client, alice, p["id"], entry_id=entry_id)
    assert first.status_code == 201 and again.status_code == 200
    assert again.json()["entry"]["id"] == entry_id and count_entries(db) == 1


def test_key_reuse_with_a_different_payload_is_rejected(client: TestClient, alice: AuthedUser) -> None:
    p = hourly_project(client, alice)
    timer_start(client, alice, p["id"], key="shared-key-123", description="A")
    r = timer_start(client, alice, p["id"], key="shared-key-123", description="B")
    assert_problem(r, 422, "IDEMPOTENCY_KEY_REUSED")


def test_keys_are_scoped_per_user(client: TestClient, alice: AuthedUser, bob: AuthedUser, db: Session) -> None:
    timer_start(client, alice, hourly_project(client, alice)["id"], key="same-key-for-both")
    r = timer_start(client, bob, hourly_project(client, bob)["id"], key="same-key-for-both")
    assert r.status_code == 201 and "Idempotent-Replayed" not in r.headers
    assert count_entries(db) == 2


def test_errors_are_not_cached(client: TestClient, alice: AuthedUser, clock: FakeClock) -> None:
    p = hourly_project(client, alice)
    running = timer_start(client, alice, p["id"]).json()["entry"]
    assert_problem(timer_start(client, alice, p["id"], key="retry-after-fix"), 409, "ACTIVE_TIMER_EXISTS")
    clock.advance(minutes=1)
    timer_cmd(client, alice, running["id"], "stop")
    clock.advance(minutes=1)
    assert timer_start(client, alice, p["id"], key="retry-after-fix").status_code == 201  # same key now succeeds


def test_manual_entry_retries(client: TestClient, alice: AuthedUser, db: Session) -> None:
    p = hourly_project(client, alice)
    a = manual_entry(client, alice, p["id"], "2026-10-11T08:00:00Z", "2026-10-11T09:00:00Z", key="manual-key-1")
    b = manual_entry(client, alice, p["id"], "2026-10-11T08:00:00Z", "2026-10-11T09:00:00Z", key="manual-key-1")
    assert a.status_code == b.status_code == 201 and a.json() == b.json() and count_entries(db) == 1
    assert_problem(
        manual_entry(client, alice, p["id"], "2026-10-11T08:00:00Z", "2026-10-11T09:00:00Z"), 409, "TIME_OVERLAP"
    )  # a NEW key is a new request


def test_key_format(client: TestClient, alice: AuthedUser) -> None:
    assert_problem(
        timer_start(client, alice, hourly_project(client, alice)["id"], key="short"), 422, "VALIDATION_ERROR"
    )


def test_expired_keys_are_purged(client: TestClient, alice: AuthedUser, db: Session, clock: FakeClock) -> None:
    p = hourly_project(client, alice)
    timer_start(client, alice, p["id"], key="old-key-0001")
    assert db.scalar(select(func.count()).select_from(IdempotencyKey)) == 1
    clock.advance(hours=49)
    # The purge shares the request's transaction: it persists with the next successful command.
    r = manual_entry(client, alice, p["id"], "2026-10-11T08:00:00Z", "2026-10-11T08:30:00Z", key="new-key-0002")
    assert r.status_code == 201
    db.expire_all()
    assert db.scalars(select(IdempotencyKey.key)).all() == ["new-key-0002"]
