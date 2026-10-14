"""Invoices and payments: lifecycle, entry locking, numbering, rounding, ownership, time zones."""

from typing import Any

from fastapi.testclient import TestClient

from tests.conftest import AuthedUser, FakeClock, register
from tests.helpers import (
    assert_problem,
    create_invoice,
    entry_at,
    make_client,
    make_project,
    new_key,
)

API = "/api/v1"


def _setup(client: TestClient, user: AuthedUser, rate: str = "85.00", currency: str = "USD") -> dict[str, Any]:
    c = make_client(client, user, "Acme", currency=currency)
    p = make_project(client, user, c["id"], "App", hourly_rate=rate)
    e1 = entry_at(client, user, p["id"], "2026-10-05T09:00:00+00:00", 90)  # 1.5 h → 127.50
    e2 = entry_at(client, user, p["id"], "2026-10-06T09:00:00+00:00", 20)  # 20 min → 28.33
    return {"client": c, "project": p, "entries": [e1, e2]}


def _send(client: TestClient, user: AuthedUser, invoice_id: str) -> dict[str, Any]:
    r = client.post(f"{API}/invoices/{invoice_id}/send", headers=user.headers)
    assert r.status_code == 200, r.text
    return r.json()  # type: ignore[no-any-return]


def _pay(client: TestClient, user: AuthedUser, invoice_id: str, amount: str, **extra: Any) -> Any:
    key = extra.pop("key", None) or new_key()
    return client.post(
        f"{API}/invoices/{invoice_id}/payments",
        json={"amount": amount, **extra},
        headers={**user.headers, "Idempotency-Key": key},
    )


def test_draft_copies_entry_amounts_and_rounds_tax_once(client: TestClient, alice: AuthedUser) -> None:
    s = _setup(client, alice)
    ids = [e["id"] for e in s["entries"]]
    r = create_invoice(
        client,
        alice,
        s["client"]["id"],
        time_entry_ids=ids,
        tax_rate="7.5",
        items=[{"description": "Setup fee", "quantity": "1", "unit_price": "0.10"}],
    )
    assert r.status_code == 201, r.text
    inv = r.json()
    assert inv["status"] == "draft" and inv["number"] is None and inv["payment_status"] is None
    assert [i["amount"] for i in inv["items"]] == ["127.50", "28.33", "0.10"]
    assert [i["kind"] for i in inv["items"]] == ["time", "time", "custom"]
    assert inv["items"][0]["quantity"] == "1.5000" and inv["items"][0]["unit_price"] == "85.00"
    assert inv["items"][0]["service_date"] == "2026-10-05" and inv["items"][0]["duration_seconds"] == 5400
    assert inv["subtotal"] == "155.93"
    assert inv["tax_amount"] == "11.69"  # 155.93 x 7.5 % = 11.69475 → 11.69
    assert inv["total"] == "167.62"
    assert inv["amount_due"] == "0.00"  # nothing is due on a draft
    assert inv["issue_date"] == "2026-10-12" and inv["due_date"] == "2026-10-26"  # default: +14 days
    assert inv["tracked_seconds"] == 5400 + 1200


def test_entries_on_an_invoice_are_locked(client: TestClient, alice: AuthedUser) -> None:
    s = _setup(client, alice)
    entry = s["entries"][0]
    inv = create_invoice(client, alice, s["client"]["id"], time_entry_ids=[entry["id"]]).json()

    current = client.get(f"{API}/time-entries/{entry['id']}", headers=alice.headers).json()
    assert current["invoice_id"] == inv["id"]
    r = client.patch(
        f"{API}/time-entries/{entry['id']}",
        json={"version": current["version"], "description": "changed"},
        headers=alice.headers,
    )
    body = assert_problem(r, 409, "ENTRY_LOCKED")
    assert body["context"]["invoice_id"] == inv["id"]
    assert_problem(client.delete(f"{API}/time-entries/{entry['id']}", headers=alice.headers), 409, "ENTRY_LOCKED")

    # A client holding the pre-invoice version still learns the real reason, not a version conflict.
    stale = client.patch(
        f"{API}/time-entries/{entry['id']}",
        json={"version": entry["version"], "description": "x"},
        headers=alice.headers,
    )
    assert_problem(stale, 409, "ENTRY_LOCKED")

    # A second invoice cannot claim the same entry.
    r = create_invoice(client, alice, s["client"]["id"], time_entry_ids=[entry["id"]])
    assert assert_problem(r, 409, "ENTRY_ALREADY_INVOICED")["context"]["time_entry_ids"] == [entry["id"]]


def test_invalid_entries_are_rejected(client: TestClient, alice: AuthedUser) -> None:
    s = _setup(client, alice)
    other = make_client(client, alice, "Other", currency="USD")
    other_project = make_project(client, alice, other["id"], "Site", hourly_rate="50.00")
    foreign = entry_at(client, alice, other_project["id"], "2026-10-07T09:00:00+00:00", 30)
    unpaid = entry_at(client, alice, s["project"]["id"], "2026-10-08T09:00:00+00:00", 30, billable=False)

    r = create_invoice(client, alice, s["client"]["id"], time_entry_ids=[foreign["id"]])
    assert assert_problem(r, 422, "INVALID_INVOICE_ENTRIES")["errors"][0]["code"] == "other_client"
    r = create_invoice(client, alice, s["client"]["id"], time_entry_ids=[unpaid["id"]])
    assert assert_problem(r, 422, "INVALID_INVOICE_ENTRIES")["errors"][0]["code"] == "not_billable"
    r = create_invoice(client, alice, s["client"]["id"], time_entry_ids=["00000000-0000-4000-8000-000000000000"])
    assert assert_problem(r, 422, "INVALID_INVOICE_ENTRIES")["errors"][0]["code"] == "not_found"
    r = create_invoice(client, alice, s["client"]["id"], currency="EUR", time_entry_ids=[s["entries"][0]["id"]])
    assert_problem(r, 422, "CURRENCY_MISMATCH")
    r = create_invoice(client, alice, s["client"]["id"], issue_date="2026-10-10", due_date="2026-10-01")
    assert r.status_code == 422
    r = create_invoice(client, alice, s["client"]["id"], tax_rate=20)  # JSON number → rejected (no floats)
    assert r.status_code == 422


def test_update_replaces_lines_and_releases_removed_entries(client: TestClient, alice: AuthedUser) -> None:
    s = _setup(client, alice)
    e1, e2 = s["entries"]
    inv = create_invoice(client, alice, s["client"]["id"], time_entry_ids=[e1["id"], e2["id"]]).json()

    r = client.patch(
        f"{API}/invoices/{inv['id']}",
        json={"version": inv["version"], "time_entry_ids": [e2["id"]], "notes": "Thanks!", "tax_rate": "10"},
        headers=alice.headers,
    )
    assert r.status_code == 200, r.text
    updated = r.json()
    assert [i["time_entry_id"] for i in updated["items"]] == [e2["id"]]
    assert updated["subtotal"] == "28.33" and updated["tax_amount"] == "2.83" and updated["total"] == "31.16"
    assert updated["notes"] == "Thanks!" and updated["version"] == inv["version"] + 1
    assert client.get(f"{API}/time-entries/{e1['id']}", headers=alice.headers).json()["invoice_id"] is None

    stale = client.patch(f"{API}/invoices/{inv['id']}", json={"version": inv["version"]}, headers=alice.headers)
    assert assert_problem(stale, 409, "VERSION_CONFLICT")["context"]["current"]["version"] == updated["version"]


def test_send_assigns_gapless_numbers_and_snapshots_the_client(client: TestClient, alice: AuthedUser) -> None:
    s = _setup(client, alice)
    e1, e2 = s["entries"]
    first = create_invoice(client, alice, s["client"]["id"], time_entry_ids=[e1["id"]]).json()
    draft = create_invoice(client, alice, s["client"]["id"], time_entry_ids=[e2["id"]]).json()
    # A deleted draft never consumed a number.
    assert client.delete(f"{API}/invoices/{draft['id']}", headers=alice.headers).status_code == 204
    second = create_invoice(client, alice, s["client"]["id"], time_entry_ids=[e2["id"]]).json()

    sent1 = _send(client, alice, first["id"])
    sent2 = _send(client, alice, second["id"])
    assert (sent1["number"], sent2["number"]) == ("INV-2026-0001", "INV-2026-0002")
    assert sent1["status"] == "sent" and sent1["payment_status"] == "unpaid"
    assert sent1["amount_due"] == sent1["total"] == "127.50"

    client.patch(f"{API}/clients/{s['client']['id']}", json={"name": "Renamed"}, headers=alice.headers)
    again = client.get(f"{API}/invoices/{first['id']}", headers=alice.headers).json()
    assert again["bill_to"]["name"] == "Acme"  # issued documents never change
    assert again["client"]["name"] == "Renamed"  # the live reference does

    assert_problem(client.post(f"{API}/invoices/{first['id']}/send", headers=alice.headers), 409, "INVALID_TRANSITION")
    r = client.patch(f"{API}/invoices/{first['id']}", json={"version": again["version"]}, headers=alice.headers)
    assert_problem(r, 409, "INVALID_TRANSITION")
    assert_problem(client.delete(f"{API}/invoices/{first['id']}", headers=alice.headers), 409, "INVALID_TRANSITION")


def test_empty_invoice_cannot_be_sent(client: TestClient, alice: AuthedUser) -> None:
    c = make_client(client, alice, "Acme")
    inv = create_invoice(client, alice, c["id"]).json()
    assert_problem(client.post(f"{API}/invoices/{inv['id']}/send", headers=alice.headers), 422, "INVOICE_EMPTY")


def test_payments_partial_full_overpayment_and_undo(client: TestClient, alice: AuthedUser, clock: FakeClock) -> None:
    s = _setup(client, alice)
    inv = create_invoice(client, alice, s["client"]["id"], time_entry_ids=[s["entries"][0]["id"]]).json()
    assert_problem(_pay(client, alice, inv["id"], "10.00"), 409, "INVALID_TRANSITION")  # draft
    _send(client, alice, inv["id"])

    key = new_key()
    r = _pay(client, alice, inv["id"], "100.00", method="card", key=key)
    assert r.status_code == 201, r.text
    partial = r.json()
    assert partial["payment_status"] == "partial" and partial["status"] == "sent"
    assert partial["amount_paid"] == "100.00" and partial["amount_due"] == "27.50"
    assert partial["payments"][0]["paid_on"] == "2026-10-12" and partial["payments"][0]["method"] == "card"

    replay = _pay(client, alice, inv["id"], "100.00", method="card", key=key)  # double tap → same result
    assert replay.headers.get("Idempotent-Replayed") == "true" and replay.json() == partial

    over = _pay(client, alice, inv["id"], "27.51")
    assert assert_problem(over, 422, "OVERPAYMENT")["context"]["amount_due"] == "27.50"
    future = _pay(client, alice, inv["id"], "1.00", paid_on="2026-10-13")
    assert future.status_code == 422
    assert _pay(client, alice, inv["id"], "0.00").status_code == 422

    paid = _pay(client, alice, inv["id"], "27.50").json()
    assert paid["status"] == "paid" and paid["payment_status"] == "paid" and paid["amount_due"] == "0.00"
    assert paid["paid_at"] is not None
    assert_problem(_pay(client, alice, inv["id"], "1.00"), 409, "INVOICE_ALREADY_PAID")

    payment_id = paid["payments"][1]["id"]
    undone = client.delete(f"{API}/invoices/{inv['id']}/payments/{payment_id}", headers=alice.headers).json()
    assert undone["status"] == "sent" and undone["payment_status"] == "partial" and undone["paid_at"] is None
    missing = client.delete(f"{API}/invoices/{inv['id']}/payments/{payment_id}", headers=alice.headers)
    assert_problem(missing, 404, "NOT_FOUND")


def test_void_releases_entries_for_a_new_invoice(client: TestClient, alice: AuthedUser) -> None:
    s = _setup(client, alice)
    entry = s["entries"][0]
    inv = create_invoice(client, alice, s["client"]["id"], time_entry_ids=[entry["id"]]).json()
    assert_problem(client.post(f"{API}/invoices/{inv['id']}/void", headers=alice.headers), 409, "INVALID_TRANSITION")
    _send(client, alice, inv["id"])

    paid = _pay(client, alice, inv["id"], "10.00").json()
    r = client.post(f"{API}/invoices/{inv['id']}/void", headers=alice.headers)
    assert_problem(r, 409, "INVOICE_HAS_PAYMENTS")
    client.delete(f"{API}/invoices/{inv['id']}/payments/{paid['payments'][0]['id']}", headers=alice.headers)

    voided = client.post(f"{API}/invoices/{inv['id']}/void", headers=alice.headers).json()
    assert voided["status"] == "void" and voided["number"] == "INV-2026-0001" and voided["amount_due"] == "0.00"
    assert voided["payment_status"] is None
    billable = client.get(
        f"{API}/invoices/billable-entries", params={"client_id": s["client"]["id"]}, headers=alice.headers
    ).json()
    assert entry["id"] in [e["id"] for e in billable["items"]]
    again = create_invoice(client, alice, s["client"]["id"], time_entry_ids=[entry["id"]])
    assert again.status_code == 201
    assert _send(client, alice, again.json()["id"])["number"] == "INV-2026-0002"  # void keeps its number


def test_billable_entries_lists_only_free_priced_work(client: TestClient, alice: AuthedUser) -> None:
    s = _setup(client, alice)
    entry_at(client, alice, s["project"]["id"], "2026-10-09T09:00:00+00:00", 30, billable=False)
    create_invoice(client, alice, s["client"]["id"], time_entry_ids=[s["entries"][1]["id"]])  # draft reserves it
    body = client.get(
        f"{API}/invoices/billable-entries", params={"client_id": s["client"]["id"]}, headers=alice.headers
    ).json()
    assert [e["id"] for e in body["items"]] == [s["entries"][0]["id"]]
    assert body["totals"] == [{"currency": "USD", "entries": 1, "seconds": 5400, "amount": "127.50"}]
    assert body["truncated"] is False
    ranged = client.get(
        f"{API}/invoices/billable-entries",
        params={"client_id": s["client"]["id"], "from": "2026-10-06", "to": "2026-10-31"},
        headers=alice.headers,
    ).json()
    assert ranged["items"] == []


def test_billable_entries_for_editing_a_draft(client: TestClient, alice: AuthedUser, bob: AuthedUser) -> None:
    s = _setup(client, alice)
    e1, e2 = (e["id"] for e in s["entries"])
    draft = create_invoice(client, alice, s["client"]["id"], time_entry_ids=[e2]).json()
    url = f"{API}/invoices/billable-entries"
    params = {"client_id": s["client"]["id"], "invoice_id": draft["id"]}

    body = client.get(url, params=params, headers=alice.headers).json()
    assert [e["id"] for e in body["items"]] == [e1, e2]  # free work + the draft's own entries
    assert body["totals"][0]["amount"] == "155.83"
    # The draft's own entries stay included even outside the date filter.
    ranged = client.get(url, params={**params, "from": "2026-10-01", "to": "2026-10-05"}, headers=alice.headers)
    assert [e["id"] for e in ranged.json()["items"]] == [e1, e2]

    # Editing flow: swap the lines, then the released entry is free again.
    r = client.patch(
        f"{API}/invoices/{draft['id']}",
        json={"version": draft["version"], "time_entry_ids": [e1], "tax_rate": "10"},
        headers=alice.headers,
    )
    assert r.status_code == 200, r.text
    assert r.json()["subtotal"] == "127.50" and r.json()["total"] == "140.25"
    free = client.get(url, params={"client_id": s["client"]["id"]}, headers=alice.headers).json()
    assert [e["id"] for e in free["items"]] == [e2]

    other = make_client(client, alice, "Globex")
    assert_problem(
        client.get(url, params={"client_id": other["id"], "invoice_id": draft["id"]}, headers=alice.headers),
        422,
        "VALIDATION_ERROR",
    )
    _send(client, alice, draft["id"])
    assert_problem(client.get(url, params=params, headers=alice.headers), 409, "INVALID_TRANSITION")
    bob_client = make_client(client, bob, "Bob Co")
    assert_problem(
        client.get(url, params={"client_id": bob_client["id"], "invoice_id": draft["id"]}, headers=bob.headers),
        404,
        "NOT_FOUND",
    )


def test_overdue_is_derived_in_the_user_time_zone(client: TestClient, clock: FakeClock) -> None:
    # 2026-10-12 10:00 UTC is already 2026-10-13 in Kiritimati (UTC+14).
    utc_user = register(client, "utc@example.com", timezone="UTC")
    far_east = register(client, "kiritimati@example.com", timezone="Pacific/Kiritimati")
    numbers = []
    for user in (utc_user, far_east):
        s = _setup(client, user)
        inv = create_invoice(
            client,
            user,
            s["client"]["id"],
            time_entry_ids=[s["entries"][0]["id"]],
            issue_date="2026-10-01",
            due_date="2026-10-12",
        ).json()
        numbers.append(_send(client, user, inv["id"]))
    assert numbers[0]["is_overdue"] is False and numbers[0]["days_overdue"] == 0
    assert numbers[1]["is_overdue"] is True and numbers[1]["days_overdue"] == 1

    listed = client.get(f"{API}/invoices", params={"status": "overdue"}, headers=far_east.headers).json()
    assert [i["id"] for i in listed["items"]] == [numbers[1]["id"]]
    assert client.get(f"{API}/invoices", params={"status": "overdue"}, headers=utc_user.headers).json()["items"] == []
    clock.advance(days=1)
    assert client.get(f"{API}/invoices", params={"status": "overdue"}, headers=utc_user.headers).json()["items"]


def test_list_filters_and_pagination(client: TestClient, alice: AuthedUser, clock: FakeClock) -> None:
    c = make_client(client, alice, "Acme")
    created = []
    for i in range(3):
        clock.advance(seconds=1)
        items = [{"description": f"Line {i}", "quantity": "1", "unit_price": "10.00"}]
        created.append(create_invoice(client, alice, c["id"], items=items).json())
    _send(client, alice, created[0]["id"])

    page1 = client.get(f"{API}/invoices", params={"limit": 2}, headers=alice.headers).json()
    assert [i["id"] for i in page1["items"]] == [created[2]["id"], created[1]["id"]]
    page2 = client.get(
        f"{API}/invoices", params={"limit": 2, "cursor": page1["next_cursor"]}, headers=alice.headers
    ).json()
    assert [i["id"] for i in page2["items"]] == [created[0]["id"]] and page2["next_cursor"] is None
    drafts = client.get(f"{API}/invoices", params={"status": "draft"}, headers=alice.headers).json()["items"]
    assert len(drafts) == 2
    assert "items" not in drafts[0]  # list rows are summaries
    sent = client.get(f"{API}/invoices", params={"status": "sent", "client_id": c["id"]}, headers=alice.headers)
    assert [i["id"] for i in sent.json()["items"]] == [created[0]["id"]]
    assert client.get(f"{API}/invoices", params={"status": "bogus"}, headers=alice.headers).status_code == 422


def test_client_stats_count_draft_entries_as_unbilled(client: TestClient, alice: AuthedUser) -> None:
    s = _setup(client, alice)
    inv = create_invoice(client, alice, s["client"]["id"], time_entry_ids=[s["entries"][0]["id"]]).json()

    def unbilled() -> list[dict[str, str]]:
        return client.get(f"{API}/clients/{s['client']['id']}", headers=alice.headers).json()["stats"]["unbilled"]  # type: ignore[no-any-return]

    assert unbilled() == [{"currency": "USD", "amount": "155.83"}]  # a draft is not billed yet
    _send(client, alice, inv["id"])
    assert unbilled() == [{"currency": "USD", "amount": "28.33"}]
    project = client.get(f"{API}/projects/{s['project']['id']}", headers=alice.headers).json()
    assert project["stats"]["unbilled"] == [{"currency": "USD", "amount": "28.33"}]
    assert project["stats"]["tracked_seconds"] == 5400 + 1200  # tracked time is unaffected


def test_pdf_renders_issued_and_draft_invoices(client: TestClient, alice: AuthedUser) -> None:
    c = make_client(client, alice, "ТОВ «Клієнт» — Їжак", currency="UAH", email="pay@example.com")
    p = make_project(client, alice, c["id"], "Мобільний застосунок", hourly_rate="1500.00")
    e = entry_at(client, alice, p["id"], "2026-10-05T09:00:00+00:00", 75, description="Екран входу, ґанок")
    inv = create_invoice(client, alice, c["id"], time_entry_ids=[e["id"]], notes="Дякуємо! Оплата за 14 днів.").json()

    draft = client.get(f"{API}/invoices/{inv['id']}/pdf", headers=alice.headers)
    assert draft.status_code == 200 and draft.headers["content-type"] == "application/pdf"
    assert draft.content.startswith(b"%PDF-") and b"%%EOF" in draft.content[-1024:]
    assert 'filename="draft-' in draft.headers["content-disposition"]

    _send(client, alice, inv["id"])
    _pay(client, alice, inv["id"], "500.00", method="bank_transfer")
    issued = client.get(f"{API}/invoices/{inv['id']}/pdf", headers=alice.headers)
    assert issued.status_code == 200 and issued.content.startswith(b"%PDF-")
    assert 'filename="INV-2026-0001.pdf"' in issued.headers["content-disposition"]
    assert issued.headers["cache-control"] == "no-store"


def test_invoices_are_private(client: TestClient, alice: AuthedUser, bob: AuthedUser) -> None:
    s = _setup(client, alice)
    inv = create_invoice(client, alice, s["client"]["id"], time_entry_ids=[s["entries"][0]["id"]]).json()
    _send(client, alice, inv["id"])
    paid = _pay(client, alice, inv["id"], "1.00").json()
    base = f"{API}/invoices/{inv['id']}"

    for method, path, body in [
        ("get", base, None),
        ("patch", base, {"version": 1}),
        ("delete", base, None),
        ("post", f"{base}/send", None),
        ("post", f"{base}/void", None),
        ("post", f"{base}/payments", {"amount": "1.00"}),
        ("delete", f"{base}/payments/{paid['payments'][0]['id']}", None),
        ("get", f"{base}/pdf", None),
    ]:
        kwargs: dict[str, Any] = {"headers": {**bob.headers, "Idempotency-Key": new_key()}}
        if body is not None:
            kwargs["json"] = body
        assert_problem(getattr(client, method)(path, **kwargs), 404, "NOT_FOUND")

    # Bob can neither bill Alice's client nor attach Alice's entries to his own invoice.
    assert_problem(create_invoice(client, bob, s["client"]["id"]), 404, "NOT_FOUND")
    bobs = make_client(client, bob, "Bob's client")
    r = create_invoice(client, bob, bobs["id"], time_entry_ids=[s["entries"][1]["id"]])
    assert assert_problem(r, 422, "INVALID_INVOICE_ENTRIES")["errors"][0]["code"] == "not_found"
    billable = client.get(
        f"{API}/invoices/billable-entries", params={"client_id": s["client"]["id"]}, headers=bob.headers
    )
    assert_problem(billable, 404, "NOT_FOUND")
    assert client.get(f"{API}/invoices", headers=bob.headers).json()["items"] == []
    assert client.get(f"{API}/invoices", headers={}).status_code == 401
