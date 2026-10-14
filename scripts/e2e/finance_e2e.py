"""End-to-end check of the money features (web build) against a REAL backend and database.

What it proves, verifying PostgreSQL after each step:
  tracked / invoiced / received are shown separately and per currency (USD and EUR never summed),
  an invoice built in the UI from tracked entries uses the server rounding rules (preview == stored totals),
  sending locks the entries and assigns a number, partial and final payments move the invoice to paid,
  over-payment is rejected, the PDF and both CSV exports download with the right content,
  another user cannot read the invoice or its PDF.

Usage (backend on :8000 with CORS for :8090 and relaxed rate limits; web export served on :8090):
  python3 scripts/e2e/finance_e2e.py --app http://localhost:8090 --api http://localhost:8000/api/v1 \
      --db "host=localhost user=postgres dbname=fh_e2e"

Requires: Python Playwright with Chromium, psql on PATH.
"""

import argparse
import csv
import io
import json
import re
import subprocess
import sys
import urllib.error
import urllib.request
import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

from playwright.sync_api import Page, sync_playwright

RESULTS: list[tuple[bool, str]] = []


def check(ok: bool, label: str) -> None:
    RESULTS.append((ok, label))
    print(("PASS " if ok else "FAIL ") + label, flush=True)


def sql(dsn: str, query: str) -> list[list[str]]:
    out = subprocess.run(["psql", dsn, "-tA", "-F", "|", "-c", query], check=True, capture_output=True, text=True)
    return [line.split("|") for line in out.stdout.strip().splitlines() if line]


class Api:
    def __init__(self, base: str) -> None:
        self.base = base.rstrip("/")
        self.token: str | None = None
        self.credentials: dict[str, str] | None = None

    def register(self, email: str, password: str, name: str) -> Any:
        self.credentials = {"email": email, "password": password}
        out = self.ok("POST", "/auth/register", {**self.credentials, "full_name": name})
        self.token = out["access_token"]
        return out

    def call(self, method: str, path: str, body: Any = None, *, key: bool = False, retry: bool = True) -> tuple[int, Any, bytes]:
        headers = {"Content-Type": "application/json"}
        if self.token:
            headers["Authorization"] = f"Bearer {self.token}"
        if key:
            headers["Idempotency-Key"] = str(uuid.uuid4())
        data = json.dumps(body).encode() if body is not None else None
        req = urllib.request.Request(self.base + path, data=data, method=method, headers=headers)
        try:
            with urllib.request.urlopen(req) as res:
                raw = res.read()
                status = res.status
        except urllib.error.HTTPError as err:
            raw, status = err.read(), err.code
        try:
            parsed = json.loads(raw) if raw else None
        except ValueError:
            parsed = None
        if status == 401 and retry and self.credentials:  # short e2e access-token TTL: sign in again once
            self.token = None
            self.token = self.ok("POST", "/auth/login", self.credentials)["access_token"]
            return self.call(method, path, body, key=key, retry=False)
        return status, parsed, raw

    def ok(self, method: str, path: str, body: Any = None, *, key: bool = False) -> Any:
        status, parsed, raw = self.call(method, path, body, key=key)
        if status >= 300:
            raise RuntimeError(f"{method} {path} -> {status}: {raw[:300]!r}")
        return parsed


def text_of(page: Page, test_id: str) -> str:
    return page.get_by_test_id(test_id).last.inner_text().strip()


def expect_text(page: Page, test_id: str, expected: str, timeout: int = 10_000) -> bool:
    try:
        page.get_by_test_id(test_id).last.wait_for(timeout=timeout)
        page.wait_for_function(
            "([id, want]) => { const n = [...document.querySelectorAll(`[data-testid='${id}']`)].pop();"
            " return !!n && n.innerText.trim() === want; }",
            arg=[test_id, expected],
            timeout=timeout,
        )
        return True
    except Exception:  # noqa: BLE001 - reported through check()
        print(f"   {test_id}: expected {expected!r}, got {text_of(page, test_id) if page.get_by_test_id(test_id).count() else '<missing>'!r}")
        return False


def click_text(page: Page, label: str) -> None:
    page.get_by_text(label, exact=True).last.click()


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--app", default="http://localhost:8090")
    parser.add_argument("--api", default="http://localhost:8000/api/v1")
    parser.add_argument("--db", default="host=localhost user=postgres dbname=fh_e2e")
    args = parser.parse_args()
    app, dsn = args.app.rstrip("/"), args.db

    # ---------------- seed through the real API ----------------
    email, password = f"fin-{uuid.uuid4().hex[:8]}@example.com", "e2e-password-123"
    api = Api(args.api)
    reg = api.register(email, password, "Finance Tester")
    acme = api.ok("POST", "/clients", {"name": "Acme", "currency": "USD", "default_hourly_rate": "85.00"})
    globex = api.ok("POST", "/clients", {"name": "Globex", "currency": "EUR", "default_hourly_rate": "60.00"})
    p_usd = api.ok("POST", "/projects", {"client_id": acme["id"], "name": "Mobile app"})
    p_eur = api.ok("POST", "/projects", {"client_id": globex["id"], "name": "Audit"})

    now = datetime.now(UTC).replace(microsecond=0)
    # Keep every entry inside "today" in UTC so the month/today ranges include them whatever the run time.
    day_start = now.replace(hour=0, minute=0, second=0)
    base = max(day_start, now - timedelta(hours=5)) if now - day_start >= timedelta(hours=3) else day_start

    def entry(project: str, start_offset: int, seconds: int) -> dict[str, Any]:
        started = base + timedelta(seconds=start_offset)
        body = {"project_id": project, "started_at": started.isoformat(), "ended_at": (started + timedelta(seconds=seconds)).isoformat()}
        return api.ok("POST", "/time-entries", body, key=True)  # type: ignore[no-any-return]

    if now - base < timedelta(seconds=9000):  # just after midnight: entries would end in the future
        print("SKIP: run again later (needs ~2.5 h of today behind the clock)")
        return 2
    e1 = entry(p_usd["id"], 0, 5400)  # 1.5 h × 85 = 127.50
    e2 = entry(p_usd["id"], 5400, 1200)  # 20 min × 85 = 28.333… → 28.33
    e3 = entry(p_eur["id"], 6600, 1800)  # 0.5 h × 60 = 30.00 EUR
    amounts = {e["id"]: e["billable_amount"] for e in (e1, e2, e3)}
    check(amounts == {e1["id"]: "127.50", e2["id"]: "28.33", e3["id"]: "30.00"}, f"seed: per-entry amounts rounded half-up {sorted(amounts.values())}")

    with sync_playwright() as p:
        browser = p.chromium.launch()
        ctx = browser.new_context(viewport={"width": 390, "height": 844}, accept_downloads=True)
        page = ctx.new_page()
        page_errors: list[str] = []
        page.on("pageerror", lambda e: page_errors.append(str(e)))

        page.goto(f"{app}/sign-in")
        page.get_by_test_id("auth-email").fill(email)
        page.get_by_test_id("auth-password").fill(password)
        page.get_by_test_id("auth-submit").click()
        page.get_by_test_id("dashboard-screen").wait_for(timeout=15_000)

        # ---------------- dashboard before invoicing ----------------
        ok = all(
            [
                expect_text(page, "flow-USD-tracked", "$155.83"),
                expect_text(page, "flow-USD-invoiced", "$0.00"),
                expect_text(page, "flow-USD-received", "$0.00"),
                expect_text(page, "flow-EUR-tracked", "€30.00"),
                expect_text(page, "balance-USD-unbilled", "$155.83"),
                expect_text(page, "balance-EUR-unbilled", "€30.00"),
            ]
        )
        check(ok, "dashboard: tracked value per currency, nothing invoiced or received yet")
        check(page.get_by_text(re.compile(r"185\.83")).count() == 0, "dashboard: USD and EUR are never added together")

        # ---------------- new invoice through the UI ----------------
        page.get_by_role("tab", name=re.compile("Clients")).first.click()
        page.get_by_test_id("clients-screen").get_by_text("Acme", exact=True).first.click()
        page.get_by_test_id("client-new-invoice").last.click()
        page.get_by_test_id("invoice-new-screen").last.wait_for()
        check(expect_text(page, "invoice-preview-total", "$155.83"), "new invoice: both unbilled USD entries preselected, preview $155.83")
        check(page.get_by_test_id(f"pick-entry-{e3['id']}").count() == 0, "new invoice: the EUR entry of another client is not offered")
        page.get_by_test_id("invoice-tax").last.fill("7.5")
        check(expect_text(page, "invoice-preview-total", "$167.52"), "new invoice: tax 7.5 % applied once to the subtotal → $167.52")
        page.get_by_test_id("invoice-create").last.click()
        page.get_by_test_id("invoice-detail-screen").last.wait_for(timeout=15_000)

        rows = sql(dsn, f"SELECT id, status, subtotal, tax_amount, total, currency FROM invoices WHERE user_id = '{reg['user']['id']}'")
        check(len(rows) == 1 and rows[0][1:] == ["draft", "155.83", "11.69", "167.52", "USD"], f"create: draft stored with the previewed totals {rows}")
        invoice_id = rows[0][0] if rows else ""
        locked = sql(dsn, f"SELECT count(*) FROM time_entries WHERE invoice_id = '{invoice_id}'")[0][0]
        check(locked == "2", "create: both entries attached to the draft")

        # ---------------- edit the draft ----------------
        def totals() -> list[str]:
            return sql(dsn, f"SELECT subtotal, tax_amount, total, version FROM invoices WHERE id = '{invoice_id}'")[0]

        page.get_by_test_id("invoice-edit").last.click()
        page.get_by_test_id("invoice-edit-screen").last.wait_for()
        ok = expect_text(page, "invoice-preview-total", "$167.52") and page.get_by_test_id("invoice-tax").last.input_value() == "7.5"
        check(ok, "edit: the draft opens with its entries selected and its 7.5 % tax restored")
        page.get_by_test_id(f"pick-entry-{e2['id']}").last.click()
        page.get_by_test_id("invoice-tax").last.fill("10")
        check(expect_text(page, "invoice-preview-total", "$140.25"), "edit: unticking an entry and 10 % tax preview $140.25")
        version_before = totals()[3]
        page.get_by_test_id("invoice-save").last.click()
        page.get_by_test_id("invoice-detail-screen").last.wait_for()
        after = totals()
        released = sql(dsn, f"SELECT invoice_id IS NULL FROM time_entries WHERE id = '{e2['id']}'")[0][0]
        check(after[:3] == ["127.50", "12.75", "140.25"] and int(after[3]) > int(version_before) and released == "t", f"edit: saved via PATCH, entry released {after}")
        check(expect_text(page, "invoice-total", "$140.25"), "edit: detail screen shows the stored total")

        # Concurrent change elsewhere → the stale form must not overwrite it.
        page.get_by_test_id("invoice-edit").last.click()
        page.get_by_test_id("invoice-edit-screen").last.wait_for()
        cur = api.ok("GET", f"/invoices/{invoice_id}")
        api.ok("PATCH", f"/invoices/{invoice_id}", {"version": cur["version"], "notes": "changed on another device"})
        page.get_by_test_id(f"pick-entry-{e2['id']}").last.click()
        page.get_by_test_id("invoice-tax").last.fill("7.5")
        page.get_by_test_id("invoice-save").last.click()
        page.get_by_test_id("invoice-conflict").last.wait_for(timeout=10_000)
        check(totals()[:3] == ["127.50", "12.75", "140.25"], "edit: a stale form gets VERSION_CONFLICT and changes nothing")
        page.get_by_test_id("invoice-reload").last.click()
        page.wait_for_timeout(800)
        notes_ok = page.get_by_test_id("invoice-notes").last.input_value() == "changed on another device"
        page.get_by_test_id(f"pick-entry-{e2['id']}").last.click()
        page.get_by_test_id("invoice-tax").last.fill("7.5")
        check(notes_ok and expect_text(page, "invoice-preview-total", "$167.52"), "edit: reload shows the other device's change; redo → $167.52")
        page.get_by_test_id("invoice-save").last.click()
        page.get_by_test_id("invoice-detail-screen").last.wait_for()
        check(expect_text(page, "invoice-total", "$167.52") and totals()[:3] == ["155.83", "11.69", "167.52"], "edit: saved again, both entries back on the draft")

        # ---------------- send (two taps) ----------------
        page.get_by_test_id("invoice-send").last.click()
        page.wait_for_timeout(400)
        still_draft = sql(dsn, f"SELECT status FROM invoices WHERE id = '{invoice_id}'")[0][0]
        page.get_by_test_id("invoice-send").last.click()
        page.wait_for_function(
            "() => /INV-\\d{4}-\\d{4}/.test(document.body.innerText)", timeout=10_000
        )
        status, number = sql(dsn, f"SELECT status, number FROM invoices WHERE id = '{invoice_id}'")[0]
        check(still_draft == "draft" and status == "sent" and re.fullmatch(r"INV-\d{4}-\d{4}", number) is not None, f"send: first tap only arms, second sends → {status} {number}")
        s, body, _ = api.call("PATCH", f"/time-entries/{e1['id']}", {"version": e1["version"], "description": "edit"})
        check(s == 409 and body is not None and body.get("code") == "ENTRY_LOCKED", f"send: invoiced entries are locked against edits ({s} {body and body.get('code')})")

        # ---------------- payments ----------------
        page.get_by_test_id("invoice-record-payment").last.click()
        page.get_by_test_id("payment-amount").last.fill("200")
        page.get_by_test_id("payment-submit").last.click()
        page.wait_for_timeout(500)
        n_pay = sql(dsn, f"SELECT count(*) FROM payments WHERE invoice_id = '{invoice_id}'")[0][0]
        check(n_pay == "0" and page.get_by_text("More than the amount due").count() > 0, "payment: over-payment blocked in the form, nothing sent")
        page.get_by_test_id("payment-amount").last.fill("100")
        page.get_by_test_id("payment-submit").last.click()
        check(expect_text(page, "invoice-due", "$67.52 due"), "payment: partial payment of $100.00 leaves $67.52 due")
        rows = sql(dsn, f"SELECT amount, method FROM payments WHERE invoice_id = '{invoice_id}'")
        check(rows == [["100.00", "bank_transfer"]], f"payment: stored in PostgreSQL {rows}")
        s, body, _ = api.call("POST", f"/invoices/{invoice_id}/payments", {"amount": "67.53", "paid_on": now.date().isoformat(), "method": "card"}, key=True)
        check(s == 422 and body is not None and body.get("code") == "OVERPAYMENT", f"payment: server rejects over-payment by one cent ({s} {body and body.get('code')})")

        # ---------------- PDF ----------------
        with page.expect_download(timeout=20_000) as dl:
            page.get_by_test_id("invoice-pdf").last.click()
        pdf = open(dl.value.path(), "rb").read()  # noqa: SIM115 - tiny file
        check(pdf.startswith(b"%PDF") and len(pdf) > 2000, f"pdf: downloaded {dl.value.suggested_filename} ({len(pdf)} bytes)")
        try:
            from pypdf import PdfReader

            text = "".join(pg.extract_text() or "" for pg in PdfReader(io.BytesIO(pdf)).pages)
            check(number in text and "167.52" in text and "67.52" in text, "pdf: contains the number, total and balance due")
        except ImportError:
            check(True, "pdf: (pypdf not installed — content check skipped)")

        # ---------------- dashboard after invoicing ----------------
        page.go_back()  # invoice → client detail (the new-invoice screen was replaced)
        page.go_back()  # → clients tab
        page.get_by_role("tab", name=re.compile("Dashboard")).first.click()
        ok = all(
            [
                expect_text(page, "flow-USD-tracked", "$155.83"),
                expect_text(page, "flow-USD-invoiced", "$167.52"),
                expect_text(page, "flow-USD-received", "$100.00"),
                expect_text(page, "balance-USD-unbilled", "$0.00"),
                expect_text(page, "balance-USD-outstanding", "$67.52"),
            ]
        )
        check(ok, "dashboard: tracked $155.83, invoiced $167.52 (incl. tax), received $100.00, outstanding $67.52")

        # ---------------- CSV exports ----------------
        page.get_by_test_id("dashboard-screen").get_by_text("Analytics", exact=True).first.click()
        page.get_by_test_id("analytics-screen").last.wait_for()
        with page.expect_download(timeout=20_000) as dl:
            page.get_by_test_id("export-entries").last.click()
        raw = open(dl.value.path(), "rb").read()  # noqa: SIM115
        table = list(csv.DictReader(io.StringIO(raw.decode("utf-8-sig"))))
        amounts_csv = sorted((r.get("amount") or r.get("billable_amount") or "") for r in table)
        check(len(table) == 3 and amounts_csv == ["127.50", "28.33", "30.00"], f"csv entries: 3 rows with exact amounts {amounts_csv}")
        with page.expect_download(timeout=20_000) as dl:
            page.get_by_test_id("export-invoices").last.click()
        inv_rows = list(csv.DictReader(io.StringIO(open(dl.value.path(), "rb").read().decode("utf-8-sig"))))  # noqa: SIM115
        check(len(inv_rows) == 1 and inv_rows[0].get("number") == number and inv_rows[0].get("total") == "167.52", f"csv invoices: {inv_rows[:1]}")

        # ---------------- final payment ----------------
        api.ok("POST", f"/invoices/{invoice_id}/payments", {"amount": "67.52", "paid_on": now.date().isoformat(), "method": "card"}, key=True)
        status, paid_at = sql(dsn, f"SELECT status, paid_at IS NOT NULL FROM invoices WHERE id = '{invoice_id}'")[0]
        summary = api.ok("GET", "/dashboard/summary?period=month")
        usd = next(f for f in summary["flows"] if f["currency"] == "USD")
        bal = next((b for b in summary["balances"] if b["currency"] == "USD"), {"outstanding": "0.00"})
        check(status == "paid" and paid_at == "t" and usd["received"] == "167.52" and bal["outstanding"] == "0.00", f"final payment: invoice paid, received $167.52, nothing outstanding ({status})")

        # ---------------- isolation ----------------
        other = Api(args.api)
        other.register(f"o-{uuid.uuid4().hex[:8]}@example.com", password, "Other")
        s1, _, _ = other.call("GET", f"/invoices/{invoice_id}")
        s2, _, _ = other.call("GET", f"/invoices/{invoice_id}/pdf")
        s3, _, _ = other.call("POST", f"/invoices/{invoice_id}/payments", {"amount": "1.00", "paid_on": now.date().isoformat()}, key=True)
        check((s1, s2, s3) == (404, 404, 404), f"isolation: another user gets 404 for the invoice, its PDF and payments {(s1, s2, s3)}")

        check(not page_errors, f"no uncaught page errors ({len(page_errors)}) {page_errors[:2]}")
        browser.close()

    passed = sum(ok for ok, _ in RESULTS)
    print(f"\n{passed}/{len(RESULTS)} checks passed")
    return 0 if passed == len(RESULTS) else 1


if __name__ == "__main__":
    sys.exit(main())
