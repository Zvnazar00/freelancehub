"""Midnight and daylight-saving boundaries.

Durations are computed on absolute UTC instants, so wall-clock jumps never change them.
Day grouping uses the user's time zone and the local date of `started_at` (assumption A-8).

Europe/Kyiv 2026: clocks go back 04:00 EEST → 03:00 EET on 25 Oct (a 25-hour day) and
forward 03:00 EET → 04:00 EEST on 29 Mar (a 23-hour day).
"""

from datetime import UTC, datetime

import pytest
from fastapi.testclient import TestClient

from tests.conftest import AuthedUser, FakeClock
from tests.helpers import assert_problem, hourly_project, manual_entry, timer_cmd, timer_start

API = "/api/v1/time-entries"


@pytest.fixture
def kyiv(client: TestClient, alice: AuthedUser) -> AuthedUser:
    assert client.patch("/api/v1/me", headers=alice.headers, json={"timezone": "Europe/Kyiv"}).status_code == 200
    return alice


def utc(text: str) -> datetime:
    return datetime.fromisoformat(text).astimezone(UTC)


def day_totals(client: TestClient, user: AuthedUser, day_from: str, day_to: str) -> dict[str, int]:
    body = client.get(API, headers=user.headers, params={"from": day_from, "to": day_to}).json()
    return {d["date"]: d["seconds"] for d in body["days"]}


class TestMidnight:
    def test_entry_crossing_midnight_belongs_to_its_start_day(
        self, client: TestClient, kyiv: AuthedUser, clock: FakeClock
    ) -> None:
        p = hourly_project(client, kyiv)
        # 23:30 → 00:30 local time (Kyiv, UTC+3 in October).
        r = manual_entry(client, kyiv, p["id"], "2026-10-11T23:30:00+03:00", "2026-10-12T00:30:00+03:00")
        assert r.status_code == 201 and r.json()["duration_seconds"] == 3600
        assert day_totals(client, kyiv, "2026-10-11", "2026-10-11") == {"2026-10-11": 3600}
        assert day_totals(client, kyiv, "2026-10-12", "2026-10-12") == {}

    def test_timer_paused_across_midnight(self, client: TestClient, kyiv: AuthedUser, clock: FakeClock) -> None:
        p = hourly_project(client, kyiv, "60.00")
        clock.set(utc("2026-10-11T23:40:00+03:00"))
        e = timer_start(client, kyiv, p["id"]).json()["entry"]
        clock.set(utc("2026-10-11T23:50:00+03:00"))
        timer_cmd(client, kyiv, e["id"], "pause")
        clock.set(utc("2026-10-12T00:20:00+03:00"))  # paused through midnight
        timer_cmd(client, kyiv, e["id"], "resume")
        clock.set(utc("2026-10-12T00:30:00+03:00"))
        stopped = timer_cmd(client, kyiv, e["id"], "stop").json()["entry"]
        assert stopped["duration_seconds"] == 20 * 60 and stopped["billable_amount"] == "20.00"
        assert day_totals(client, kyiv, "2026-10-11", "2026-10-12") == {"2026-10-11": 1200}

    def test_the_same_instant_is_a_different_day_for_another_time_zone(
        self, client: TestClient, kyiv: AuthedUser
    ) -> None:
        p = hourly_project(client, kyiv)
        manual_entry(client, kyiv, p["id"], "2026-10-12T02:00:00Z", "2026-10-12T03:00:00Z")
        assert day_totals(client, kyiv, "2026-10-12", "2026-10-12") == {"2026-10-12": 3600}  # 05:00 in Kyiv
        client.patch("/api/v1/me", headers=kyiv.headers, json={"timezone": "America/New_York"})
        assert day_totals(client, kyiv, "2026-10-11", "2026-10-11") == {"2026-10-11": 3600}  # 22:00 the day before


class TestDaylightSaving:
    def test_fall_back_hour_counts_twice_on_the_wall_but_once_in_reality(
        self, client: TestClient, kyiv: AuthedUser, clock: FakeClock
    ) -> None:
        p = hourly_project(client, kyiv, "100.00")
        clock.set(utc("2026-10-25T02:30:00+03:00"))  # 23:30Z
        e = timer_start(client, kyiv, p["id"]).json()["entry"]
        clock.set(utc("2026-10-25T03:30:00+02:00"))  # 01:30Z — wall clock moved only 1h
        stopped = timer_cmd(client, kyiv, e["id"], "stop").json()["entry"]
        assert stopped["duration_seconds"] == 2 * 3600 and stopped["billable_amount"] == "200.00"

    def test_ambiguous_wall_time_is_disambiguated_by_offset(
        self, client: TestClient, kyiv: AuthedUser, clock: FakeClock
    ) -> None:
        clock.set(utc("2026-10-26T12:00:00Z"))
        p = hourly_project(client, kyiv)
        # "03:30" happens twice on 25 Oct; the explicit offsets make it exactly one hour.
        r = manual_entry(client, kyiv, p["id"], "2026-10-25T03:30:00+03:00", "2026-10-25T03:30:00+02:00")
        assert r.status_code == 201 and r.json()["duration_seconds"] == 3600

    def test_spring_forward_skipped_hour_is_not_billed(
        self, client: TestClient, kyiv: AuthedUser, clock: FakeClock
    ) -> None:
        p = hourly_project(client, kyiv, "100.00")
        clock.set(utc("2026-03-29T02:30:00+02:00"))  # 00:30Z
        e = timer_start(client, kyiv, p["id"]).json()["entry"]
        clock.set(utc("2026-03-29T04:30:00+03:00"))  # 01:30Z — wall clock moved 2h
        stopped = timer_cmd(client, kyiv, e["id"], "stop").json()["entry"]
        assert stopped["duration_seconds"] == 3600 and stopped["billable_amount"] == "100.00"

    def test_24h_manual_limit_uses_real_hours(self, client: TestClient, kyiv: AuthedUser, clock: FakeClock) -> None:
        clock.set(utc("2026-10-27T12:00:00Z"))
        p = hourly_project(client, kyiv)
        # Local midnight to midnight on the 25-hour day is 25 real hours → rejected.
        body = assert_problem(
            manual_entry(client, kyiv, p["id"], "2026-10-25T00:00:00+03:00", "2026-10-26T00:00:00+02:00"),
            422,
            "VALIDATION_ERROR",
        )
        assert body["errors"][0]["code"] == "duration_too_long"
        # Midnight to midnight on the 23-hour spring day is 23 real hours → fine.
        r = manual_entry(client, kyiv, p["id"], "2026-03-29T00:00:00+02:00", "2026-03-30T00:00:00+03:00")
        assert r.status_code == 201 and r.json()["duration_seconds"] == 23 * 3600

    def test_day_filter_covers_the_whole_25_hour_day(
        self, client: TestClient, kyiv: AuthedUser, clock: FakeClock
    ) -> None:
        clock.set(utc("2026-10-27T12:00:00Z"))
        p = hourly_project(client, kyiv)
        manual_entry(client, kyiv, p["id"], "2026-10-24T23:30:00+03:00", "2026-10-24T23:50:00+03:00")  # day before
        manual_entry(client, kyiv, p["id"], "2026-10-25T00:10:00+03:00", "2026-10-25T00:40:00+03:00")  # first minutes
        manual_entry(client, kyiv, p["id"], "2026-10-25T23:30:00+02:00", "2026-10-25T23:50:00+02:00")  # 25th hour side
        manual_entry(client, kyiv, p["id"], "2026-10-26T00:05:00+02:00", "2026-10-26T00:15:00+02:00")  # next day
        body = client.get(API, headers=kyiv.headers, params={"from": "2026-10-25", "to": "2026-10-25"}).json()
        assert body["days"] == [{"date": "2026-10-25", "seconds": 50 * 60, "entries": 2}]
        assert len(body["items"]) == 2
