"""Real concurrency and restarts. These tests use the full HTTP stack with real commits (no rollback
wrapper): each thread has its own TestClient and DB connection, and requests are released together."""

import threading
import uuid
from collections.abc import Callable, Iterator
from datetime import UTC, datetime, timedelta
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import Engine, func, select, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.clock import get_clock
from app.core.config import Settings, get_settings
from app.db.session import get_engine, get_session_factory
from app.main import create_app
from app.models import TimeEntry, TimeEntryPause
from tests.conftest import FakeClock, register
from tests.helpers import hourly_project, timer_cmd, timer_start


def fresh_app(settings: Settings, clock: Callable[[], datetime] | None = None) -> Any:
    """A brand-new application instance using the real DB session factory (simulates a server process)."""
    application = create_app(settings)
    application.dependency_overrides[get_settings] = lambda: settings
    if clock is not None:
        application.dependency_overrides[get_clock] = lambda: clock
    return application


@pytest.fixture
def live(engine: Engine, settings: Settings) -> Iterator[Any]:
    get_engine.cache_clear()
    get_session_factory.cache_clear()
    yield fresh_app(settings)
    with engine.begin() as conn:
        conn.execute(text("TRUNCATE users CASCADE"))
    get_engine().dispose()
    get_engine.cache_clear()
    get_session_factory.cache_clear()


def race(n: int, fn: Callable[[int], Any]) -> list[Any]:
    barrier = threading.Barrier(n)
    results: list[Any] = [None] * n

    def worker(i: int) -> None:
        barrier.wait()
        try:
            results[i] = fn(i)
        except Exception as exc:  # pragma: no cover - surfaced by assertions
            results[i] = exc

    threads = [threading.Thread(target=worker, args=(i,)) for i in range(n)]
    for t in threads:
        t.start()
    for t in threads:
        t.join(timeout=60)
    return results


def active_count(engine: Engine) -> int:
    with Session(engine) as s:
        return (
            s.scalar(select(func.count()).select_from(TimeEntry).where(TimeEntry.status.in_(["running", "paused"])))
            or 0
        )


def total_count(engine: Engine) -> int:
    with Session(engine) as s:
        return s.scalar(select(func.count()).select_from(TimeEntry)) or 0


def test_concurrent_starts_create_exactly_one_active_timer(live: Any, engine: Engine) -> None:
    with TestClient(live) as c:
        user = register(c, "race-start@example.com")
        project = hourly_project(c, user)

    def attempt(_: int) -> Any:
        with TestClient(live) as c:
            return timer_start(c, user, project["id"])

    responses = race(8, attempt)
    statuses = sorted(r.status_code for r in responses)
    assert statuses == [201] + [409] * 7, statuses
    assert {r.json()["code"] for r in responses if r.status_code == 409} == {"ACTIVE_TIMER_EXISTS"}
    assert active_count(engine) == 1 and total_count(engine) == 1


def test_concurrent_duplicates_with_the_same_key_are_one_request(live: Any, engine: Engine) -> None:
    with TestClient(live) as c:
        user = register(c, "race-dup@example.com")
        project = hourly_project(c, user)
    key, entry_id = str(uuid.uuid4()), str(uuid.uuid4())

    def attempt(_: int) -> Any:
        with TestClient(live) as c:
            return timer_start(c, user, project["id"], key=key, entry_id=entry_id)

    responses = race(8, attempt)
    assert {r.status_code for r in responses} == {201}
    assert len({r.text for r in responses}) == 1  # identical bodies
    assert sum(r.headers.get("Idempotent-Replayed") == "true" for r in responses) == 7
    assert total_count(engine) == 1


def test_concurrent_retries_with_the_same_entry_id_and_new_keys(live: Any, engine: Engine) -> None:
    with TestClient(live) as c:
        user = register(c, "race-id@example.com")
        project = hourly_project(c, user)
    entry_id = str(uuid.uuid4())

    def attempt(_: int) -> Any:
        with TestClient(live) as c:
            return timer_start(c, user, project["id"], entry_id=entry_id)

    statuses = sorted(r.status_code for r in race(6, attempt))
    assert statuses == [200] * 5 + [201]
    assert total_count(engine) == 1


def test_concurrent_commands_on_one_timer_stay_consistent(live: Any, engine: Engine) -> None:
    with TestClient(live) as c:
        user = register(c, "race-cmd@example.com")
        project = hourly_project(c, user)
        entry = timer_start(c, user, project["id"], at=(datetime.now(UTC) - timedelta(minutes=30)).isoformat()).json()[
            "entry"
        ]
    commands = ["pause", "stop", "pause", "resume", "stop", "pause"]

    def attempt(i: int) -> Any:
        with TestClient(live) as c:
            return timer_cmd(c, user, entry["id"], commands[i])

    responses = race(len(commands), attempt)
    assert all(r.status_code in (200, 409) for r in responses), [r.text for r in responses]
    assert sum(r.status_code == 200 and r.json()["entry"]["status"] == "stopped" for r in responses) == 1
    with Session(engine) as s:
        stored = s.get(TimeEntry, uuid.UUID(entry["id"]))
        assert stored is not None and stored.status == "stopped"
        open_pauses = s.scalar(
            select(func.count())
            .select_from(TimeEntryPause)
            .where(TimeEntryPause.time_entry_id == stored.id, TimeEntryPause.resumed_at.is_(None))
        )
        assert open_pauses == 0
        assert stored.duration_seconds is not None and 0 < stored.duration_seconds <= 30 * 60 + 5


def test_database_rejects_a_second_active_entry_even_without_the_service(live: Any, engine: Engine) -> None:
    """Defence in depth: the partial unique index and the exclusion constraint hold for raw SQL too."""
    with TestClient(live) as c:
        user = register(c, "raw-sql@example.com")
        project = hourly_project(c, user)
        timer_start(c, user, project["id"])
    insert = text(
        "INSERT INTO time_entries (id, user_id, project_id, source, status, started_at, billable, currency, "
        "rate_source) VALUES (gen_random_uuid(), :u, :p, 'timer', :status, :start, true, 'USD', 'none')"
    )
    # Two open-ended active entries always overlap, so either guard may fire first; both enforce the invariant.
    with (
        engine.connect() as conn,
        pytest.raises(IntegrityError, match=r"ux_time_entries_one_active|ex_time_entries_no_overlap"),
    ):
        conn.execute(
            insert, {"u": user.id, "p": project["id"], "status": "paused", "start": datetime(2020, 1, 1, tzinfo=UTC)}
        )
    stopped_insert = text(
        "INSERT INTO time_entries (id, user_id, project_id, source, status, started_at, ended_at, duration_seconds, "
        "billable, currency, rate_source) VALUES (gen_random_uuid(), :u, :p, 'manual', 'stopped', :s, :e, 60, true, "
        "'USD', 'none')"
    )
    now = datetime.now(UTC)
    with engine.connect() as conn, pytest.raises(IntegrityError, match="ex_time_entries_no_overlap"):
        conn.execute(
            stopped_insert,
            {"u": user.id, "p": project["id"], "s": now + timedelta(minutes=1), "e": now + timedelta(minutes=2)},
        )


class TestRestart:
    def test_active_timer_survives_a_server_restart(self, live: Any, settings: Settings, engine: Engine) -> None:
        clock = FakeClock(datetime.now(UTC).replace(microsecond=0))
        first_process = fresh_app(settings, clock)
        with TestClient(first_process) as c:
            user = register(c, "restart@example.com")
            project = hourly_project(c, user, "60.00")
            entry = timer_start(c, user, project["id"]).json()["entry"]
            clock.advance(minutes=40)
            timer_cmd(c, user, entry["id"], "pause")

        # "Restart": drop every pooled connection and cached engine, start a new application instance.
        get_engine().dispose()
        get_engine.cache_clear()
        get_session_factory.cache_clear()
        clock.advance(hours=5)  # downtime while paused must not count
        second_process = fresh_app(settings, clock)
        with TestClient(second_process) as c:
            state = c.get("/api/v1/timer/current", headers=user.headers).json()
            assert state["entry"]["id"] == entry["id"] and state["entry"]["status"] == "paused"
            assert state["entry"]["elapsed_seconds"] == 40 * 60  # derived from stored timestamps, not a counter
            timer_cmd(c, user, entry["id"], "resume")
            clock.advance(minutes=20)
            stopped = timer_cmd(c, user, entry["id"], "stop").json()["entry"]
        assert stopped["duration_seconds"] == 60 * 60 and stopped["billable_amount"] == "60.00"

    def test_running_timer_keeps_counting_while_the_server_is_down(self, live: Any, settings: Settings) -> None:
        clock = FakeClock(datetime.now(UTC).replace(microsecond=0))
        with TestClient(fresh_app(settings, clock)) as c:
            user = register(c, "restart-running@example.com")
            entry = timer_start(c, user, hourly_project(c, user)["id"]).json()["entry"]
        get_engine().dispose()
        get_engine.cache_clear()
        get_session_factory.cache_clear()
        clock.advance(hours=3)
        with TestClient(fresh_app(settings, clock)) as c:
            state = c.get("/api/v1/timer/current", headers=user.headers).json()
        assert state["entry"]["id"] == entry["id"] and state["entry"]["elapsed_seconds"] == 3 * 3600
