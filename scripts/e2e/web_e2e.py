"""End-to-end check of the mobile app (web build) against a REAL backend and database.

What it proves, with database verification after each timer command:
  auth forms (client + server validation), sign-up, client/project creation through the UI,
  start -> pause -> resume -> stop, elapsed time after the tab was in the background,
  an access-token expiry handled by one shared refresh, a failed command rolled back,
  timer restored from the server after a reload, no tokens in browser storage, sign-out revocation.

Usage (backend on :8000 with ACCESS_TOKEN_TTL_SECONDS=20 and CORS for :8090; web export served on :8090):
  python3 scripts/e2e/web_e2e.py --app http://localhost:8090 --db "host=localhost user=postgres dbname=fh_e2e"

Requires: Python Playwright with Chromium, psql on PATH.
"""

import argparse
import json
import re
import subprocess
import sys
import time
import uuid
from collections.abc import Callable
from typing import Any

from playwright.sync_api import Page, sync_playwright

RESULTS: list[tuple[bool, str]] = []


def check(ok: bool, label: str) -> None:
    RESULTS.append((ok, label))
    print(("PASS " if ok else "FAIL ") + label, flush=True)


def sql(dsn: str, query: str) -> list[list[str]]:
    out = subprocess.run(["psql", dsn, "-tA", "-F", "|", "-c", query], check=True, capture_output=True, text=True)
    return [line.split("|") for line in out.stdout.strip().splitlines() if line]


def net_seconds(dsn: str, entry_id: str, until: str = "now()") -> int:
    """Net seconds of an entry computed in SQL from the stored timestamps and pause intervals."""
    query = (
        f"SELECT floor(extract(epoch FROM ({until} - e.started_at)) "
        "- coalesce(sum(extract(epoch FROM (p.resumed_at - p.paused_at))), 0)) "
        "FROM time_entries e LEFT JOIN time_entry_pauses p ON p.time_entry_id = e.id "
        f"WHERE e.id = '{entry_id}' GROUP BY e.started_at, e.ended_at"
    )
    return int(sql(dsn, query)[0][0])


def wait_for(predicate: Callable[[], bool], timeout: float = 10.0, step: float = 0.25) -> bool:
    deadline = time.time() + timeout
    while time.time() < deadline:
        if predicate():
            return True
        time.sleep(step)
    return predicate()


def go_tab(page: Page, label: str) -> None:
    """In-app navigation (a full page load would end the memory-only web session)."""
    for locator in (page.get_by_role("tab", name=re.compile(label)), page.get_by_role("link", name=re.compile(label))):
        if locator.count():
            locator.first.click()
            return
    page.get_by_text(label, exact=True).last.click()


def clock_seconds(page: Page) -> int:
    text = page.get_by_test_id("time-screen").get_by_test_id("timer-display").inner_text().strip()
    h, m, s = (int(x) for x in text.split(":"))
    return h * 3600 + m * 60 + s


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--app", default="http://localhost:8090")
    parser.add_argument("--db", default="host=localhost user=postgres dbname=fh_e2e")
    parser.add_argument("--access-ttl", type=int, default=20, help="ACCESS_TOKEN_TTL_SECONDS of the backend")
    args = parser.parse_args()
    app, dsn = args.app.rstrip("/"), args.db

    email = f"e2e-{uuid.uuid4().hex[:8]}@example.com"
    password = "e2e-password-123"
    tokens: set[str] = set()

    with sync_playwright() as p:
        browser = p.chromium.launch()
        ctx = browser.new_context(viewport={"width": 390, "height": 844})
        page = ctx.new_page()
        page_errors: list[str] = []
        page.on("pageerror", lambda e: page_errors.append(str(e)))
        requests: list[str] = []
        page.on("request", lambda r: requests.append(f"{r.method} {r.url}"))

        def capture_tokens(response: Any) -> None:
            if "/auth/" in response.url and response.ok:
                try:
                    body = response.json()
                except Exception:  # noqa: BLE001 - 204 responses have no body
                    return
                for key in ("access_token", "refresh_token"):
                    if isinstance(body, dict) and body.get(key):
                        tokens.add(body[key])

        page.on("response", capture_tokens)

        # ---------------- auth ----------------
        page.goto(f"{app}/sign-up")
        page.get_by_test_id("sign-up-screen").wait_for()
        before = len([r for r in requests if "/auth/register" in r])
        page.get_by_test_id("auth-submit").click()
        page.wait_for_timeout(500)
        check(
            page.get_by_text("Name is required").count() > 0
            and len([r for r in requests if "/auth/register" in r]) == before,
            "sign-up: client-side validation blocks an empty form without calling the API",
        )

        page.get_by_test_id("auth-name").fill("E2E Tester")
        page.get_by_test_id("auth-email").fill(email)
        page.get_by_test_id("auth-password").fill(password)
        page.get_by_test_id("auth-submit").click()
        page.get_by_test_id("dashboard-screen").wait_for(timeout=15000)
        user_id = sql(dsn, f"SELECT id FROM users WHERE email = '{email}'")[0][0]
        check(bool(user_id), "sign-up: account created in PostgreSQL and the dashboard opened")

        dup = browser.new_context().new_page()
        dup.goto(f"{app}/sign-up")
        dup.get_by_test_id("auth-name").fill("Dup")
        dup.get_by_test_id("auth-email").fill(email.upper())
        dup.get_by_test_id("auth-password").fill(password)
        dup.get_by_test_id("auth-submit").click()
        check(
            wait_for(lambda: dup.get_by_text("An account with this email already exists.").count() > 0),
            "sign-up: server error EMAIL_TAKEN is shown on the email field",
        )
        dup.goto(f"{app}/sign-in")
        dup.get_by_test_id("auth-email").fill(email)
        dup.get_by_test_id("auth-password").fill("wrong-password-1")
        dup.get_by_test_id("auth-submit").click()
        check(
            wait_for(lambda: dup.get_by_text("Wrong email or password.").count() > 0),
            "sign-in: wrong password shows INVALID_CREDENTIALS",
        )
        dup.context.close()

        # ---------------- client + project through the forms ----------------
        go_tab(page, "Clients")
        page.get_by_test_id("add-client").click()
        page.get_by_test_id("client-name").fill("Northwind E2E")
        page.get_by_test_id("client-rate").fill("50")
        page.get_by_test_id("client-submit").click()
        check(
            wait_for(lambda: bool(sql(dsn, f"SELECT 1 FROM clients WHERE user_id = '{user_id}'"))),
            "client form: client stored via POST /clients",
        )

        # The new client's detail screen offers "Add project" with the client preselected.
        page.get_by_test_id("client-detail-screen").wait_for(timeout=15000)
        page.get_by_test_id("client-add-project").click()
        page.get_by_test_id("new-project-screen").wait_for()
        page.get_by_test_id("project-name").fill("Mobile app E2E")
        page.get_by_test_id("project-rate").fill("60")
        page.get_by_test_id("project-submit").click()
        check(
            wait_for(
                lambda: bool(sql(dsn, f"SELECT 1 FROM projects WHERE user_id = '{user_id}' AND hourly_rate = 60"))
            ),
            "project form: hourly project (60.00) stored via POST /projects",
        )

        # ---------------- timer ----------------
        page.get_by_test_id("project-detail-screen").wait_for(timeout=15000)
        for _ in range(4):  # back through project → client → tabs (history navigation keeps the session)
            if (
                page.get_by_test_id("project-detail-screen").count() == 0
                and page.get_by_test_id("client-detail-screen").count() == 0
                and page.get_by_test_id("new-project-screen").count() == 0
            ):
                break
            page.go_back()
            page.wait_for_timeout(700)
        go_tab(page, "Time")
        page.get_by_test_id("time-screen").wait_for()
        page.get_by_test_id("time-screen").get_by_test_id("project-selector").click()
        page.get_by_role("radio", name=re.compile("Mobile app E2E")).click()
        page.get_by_role("button", name="Done").click()
        page.get_by_test_id("time-screen").get_by_test_id("timer-start").click()

        def entry() -> list[str]:
            rows = sql(
                dsn,
                "SELECT id, status, started_at, ended_at, duration_seconds, billable_amount, "
                "hourly_rate_snapshot, version FROM time_entries "
                f"WHERE user_id = '{user_id}' ORDER BY created_at DESC LIMIT 1",
            )
            return rows[0] if rows else []

        check(wait_for(lambda: entry()[1:2] == ["running"]), "start: running entry in the database")
        entry_id = entry()[0]
        check(entry()[6] == "60.00", "start: hourly rate snapshot 60.00 stored on the entry")
        check(
            wait_for(lambda: page.get_by_test_id("time-screen").get_by_test_id("timer-pause").count() > 0),
            "start: UI switched to running",
        )

        page.wait_for_timeout(3000)
        page.get_by_test_id("time-screen").get_by_test_id("timer-pause").click()
        check(
            wait_for(
                lambda: (
                    entry()[1] == "paused"
                    and bool(
                        sql(
                            dsn,
                            f"SELECT 1 FROM time_entry_pauses WHERE time_entry_id = '{entry_id}' "
                            "AND resumed_at IS NULL",
                        )
                    )
                )
            ),
            "pause: entry paused with an open pause interval",
        )
        frozen = clock_seconds(page)
        page.wait_for_timeout(3000)
        check(abs(clock_seconds(page) - frozen) <= 0, "pause: displayed time is frozen while paused")

        page.get_by_test_id("time-screen").get_by_test_id("timer-resume").click()
        check(
            wait_for(
                lambda: (
                    entry()[1] == "running"
                    and not sql(
                        dsn,
                        f"SELECT 1 FROM time_entry_pauses WHERE time_entry_id = '{entry_id}' AND resumed_at IS NULL",
                    )
                )
            ),
            "resume: entry running again, pause interval closed",
        )

        # "Background" the app for 6 s: freeze the page's JS like a mobile OS suspends a backgrounded app
        # (no timers, no renders). Nothing may tick during this time; the value must come from timestamps.
        cdp = ctx.new_cdp_session(page)
        cdp.send("Page.setWebLifecycleState", {"state": "frozen"})
        time.sleep(6)
        cdp.send("Page.setWebLifecycleState", {"state": "active"})
        page.wait_for_timeout(1500)
        expected = net_seconds(dsn, entry_id)
        shown = clock_seconds(page)
        check(
            abs(shown - expected) <= 2,
            f"background: after 6 s frozen the timer shows {shown}s, timestamps say {expected}s (±2s)",
        )

        # Failed command: block timer commands → optimistic pause must roll back, DB unchanged.
        page.route("**/api/v1/timer/*/pause", lambda route: route.abort())
        page.get_by_test_id("time-screen").get_by_test_id("timer-pause").click()
        check(
            wait_for(lambda: page.get_by_test_id("time-screen").get_by_test_id("timer-error").count() > 0, timeout=15),
            "network failure: error shown after the retries",
        )
        check(
            page.get_by_test_id("time-screen").get_by_test_id("timer-pause").count() > 0 and entry()[1] == "running",
            "network failure: optimistic pause rolled back; database still running",
        )
        page.unroute("**/api/v1/timer/*/pause")

        # Access token expiry: wait past the TTL, then trigger several queries at once.
        time.sleep(args.access_ttl + 2)
        refresh_before = len([r for r in requests if r.endswith("/auth/refresh")])
        page.reload()  # web: the refresh token is memory-only, so a reload ends the session by design
        page.get_by_test_id("sign-in-screen").wait_for(timeout=15000)
        check(True, "reload (web): session not kept in browser storage, sign-in required by design")
        page.get_by_test_id("auth-email").fill(email)
        page.get_by_test_id("auth-password").fill(password)
        page.get_by_test_id("auth-submit").click()
        page.get_by_test_id("dashboard-screen").wait_for(timeout=15000)
        go_tab(page, "Time")
        page.get_by_test_id("time-screen").wait_for(timeout=15000)
        check(
            wait_for(lambda: page.get_by_test_id("time-screen").get_by_test_id("timer-pause").count() > 0),
            "restore: running timer restored from GET /timer/current after reload + sign-in",
        )
        expected = net_seconds(dsn, entry_id)
        check(abs(clock_seconds(page) - expected) <= 2, "restore: elapsed time derived from stored timestamps (±2s)")

        time.sleep(args.access_ttl + 2)  # let the new access token expire while staying in the app
        refresh_before = len([r for r in requests if r.endswith("/auth/refresh")])
        # Opening a client mounts a new screen with several queries at once (client, its projects).
        go_tab(page, "Clients")
        page.get_by_test_id("clients-screen").get_by_text("Northwind E2E").first.click()
        page.get_by_test_id("client-detail-screen").wait_for(timeout=15000)
        page.wait_for_timeout(2500)
        refreshes = len([r for r in requests if r.endswith("/auth/refresh")]) - refresh_before
        check(
            refreshes == 1
            and not page.get_by_test_id("sign-in-screen").count()
            and page.get_by_test_id("client-detail-screen").get_by_text("Mobile app E2E").count() > 0,
            f"token expiry: concurrent requests shared one refresh ({refreshes} refresh call), data loaded",
        )
        page.go_back()
        page.wait_for_timeout(700)

        go_tab(page, "Time")
        page.get_by_test_id("time-screen").get_by_test_id("timer-stop").click()
        check(wait_for(lambda: entry()[1] == "stopped"), "stop: entry stopped in the database")
        row = entry()
        duration, amount = int(row[4]), row[5]
        net = net_seconds(dsn, entry_id, until="e.ended_at")
        expected_amount = sql(dsn, f"SELECT round({duration} * 60.00 / 3600, 2)")[0][0]
        check(
            duration == net and amount == expected_amount,
            f"stop: duration {duration}s excludes pauses, amount {amount} = round_half_up(seconds × 60/h)",
        )
        check(
            len(sql(dsn, f"SELECT 1 FROM idempotency_keys WHERE user_id = '{user_id}'")) >= 4,
            "commands carried Idempotency-Keys (stored server-side)",
        )

        # ---------------- storage + sign-out ----------------
        storage = page.evaluate("""() => JSON.stringify({
            local: Object.fromEntries(Object.entries(localStorage)),
            session: Object.fromEntries(Object.entries(sessionStorage)),
            cookie: document.cookie })""")
        idb = page.evaluate("async () => (indexedDB.databases ? (await indexedDB.databases()).map(d => d.name) : [])")
        leaked = [t for t in tokens if t in storage]
        check(
            bool(tokens) and not leaked and not json.loads(storage)["cookie"] and not idb,
            f"no auth tokens in localStorage/sessionStorage/cookies/IndexedDB ({len(tokens)} tokens checked)",
        )

        go_tab(page, "Settings")
        page.get_by_test_id("sign-out").click()
        page.get_by_test_id("sign-in-screen").wait_for(timeout=15000)
        live = sql(
            dsn,
            f"SELECT count(*) FROM refresh_tokens WHERE user_id = '{user_id}' AND revoked_at IS NULL "
            "AND family_id = (SELECT family_id FROM refresh_tokens WHERE user_id = "
            f"'{user_id}' ORDER BY created_at DESC LIMIT 1)",
        )[0][0]
        check(live == "0", "sign-out: current session family revoked on the server")

        check(not page_errors, f"no uncaught page errors ({len(page_errors)})")
        browser.close()

    failed = [label for ok, label in RESULTS if not ok]
    print(f"\n{len(RESULTS) - len(failed)}/{len(RESULTS)} checks passed")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
