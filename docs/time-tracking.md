# FreelanceHub — Time-Tracking Engine

> Status: **implemented** (`backend/app/services/time_entries.py`, migration `0004`). This document is the contract:
> every invariant below names the mechanism that enforces it and the test that proves it.
> Related: [architecture.md §7](architecture.md) · [database.md §3.6–3.8](database.md) · [api.md §4.6–4.7](api.md)

## 1. Model in one paragraph

A time entry stores **authoritative UTC instants**: `started_at`, `ended_at`, and pause intervals in
`time_entry_pauses`. Nothing counts seconds. Elapsed time is always *derived*:
`net = (end − started_at) − Σ pauses clipped to [started_at, end]`, floored to whole seconds, where
`end = ended_at` once stopped and *server time* while active. On stop, `duration_seconds` and `billable_amount`
are computed once from the **rate snapshot taken at creation** and stored.

## 2. State machine

```
           start                 pause                resume
[none] ───────────▶ running ───────────▶ paused ───────────▶ running
                       │                    │
                  stop │               stop │ (open pause closed at stop time)
                       ▼                    ▼
                    stopped ◀──────── (edit / delete via /time-entries)
running|paused ──discard──▶ [deleted]          manual create ──▶ stopped
```

| Command | Endpoint | Allowed from | Error otherwise |
|---|---|---|---|
| start | `POST /timer/start` | no active entry | `409 ACTIVE_TIMER_EXISTS` (+ `context.active_entry`) |
| pause | `POST /timer/{id}/pause` | running | `409 INVALID_TRANSITION` |
| resume | `POST /timer/{id}/resume` | paused | `409 INVALID_TRANSITION` |
| stop | `POST /timer/{id}/stop` | running, paused | `409 INVALID_TRANSITION` |
| discard | `POST /timer/{id}/discard` | running, paused | `409 INVALID_TRANSITION` |
| edit active | `PATCH /timer/{id}` | running, paused | `409 INVALID_TRANSITION` |
| manual create | `POST /time-entries` | — | `409 TIME_OVERLAP`, `422` |
| edit stopped | `PATCH /time-entries/{id}` | stopped | `409 INVALID_TRANSITION` / `VERSION_CONFLICT` |
| delete | `DELETE /time-entries/{id}` | stopped | `409 INVALID_TRANSITION` |

A command addressed to a stopped entry while a *different* entry is active returns `409 TIMER_MISMATCH`
with the active entry, so a delayed "stop" from a phone can never stop a timer started later on a laptop.

## 3. Invariants

| # | Invariant | Enforced by | Proven by |
|---|---|---|---|
| I-1 | At most one active (running **or paused**) entry per user | Per-user lock (I-6) + check in service; partial unique index `ux_time_entries_one_active`; exclusion constraint (an active entry is open-ended) | `test_timer.py::TestInvariants::test_only_one_active_timer`, `test_timer_concurrency.py::test_concurrent_starts_create_exactly_one_active_timer`, `::test_database_rejects_a_second_active_entry_even_without_the_service` |
| I-2 | A user's entries never overlap in time | Service pre-check (friendly error with `conflicting_entry`); `EXCLUDE USING gist (user_id WITH =, tstzrange(started_at, ended_at, '[)') WITH &&)` | `test_time_entries.py::TestManual::test_overlaps_are_rejected_with_the_conflicting_entry`, `::test_running_timer_blocks_entries_after_its_start`, `::TestEdit::test_edit_cannot_create_overlap_or_break_limits` |
| I-3 | Elapsed time is derived from stored timestamps, never from a counter; paused time is excluded | `timekeeping.net_seconds`; pauses persisted; one open pause per entry (`ux_pauses_one_open`) | `tests/unit/test_timekeeping.py`, `test_timer.py::TestLifecycle::*`, `test_timer_concurrency.py::TestRestart::*` |
| I-4 | All timestamps are absolute UTC instants; durations ignore wall-clock effects (midnight, DST, user time zone) | `TIMESTAMPTZ` + DB session `timezone=UTC`; only aware datetimes accepted (naive → 422); arithmetic on instants | `test_timezones.py::TestDaylightSaving::*`, `::TestMidnight::*`, `test_timer.py::TestClientTimestamps::test_naive_timestamps_are_rejected` |
| I-5 | Timestamps are server-authoritative; a client `at` is accepted only within bounds | `effective_time`: > now + 60 s → `TIMESTAMP_IN_FUTURE`; 0–60 s ahead → clamped to now; before the last transition → `TIMESTAMP_OUT_OF_ORDER`; start > 7 days ago → `TIMESTAMP_TOO_OLD` | `test_timer.py::TestClientTimestamps::*` |
| I-6 | Commands of one user are serialised; the clock is read **after** the lock | `SELECT … FROM users FOR NO KEY UPDATE` at the start of every command, then `clock()` | `test_timer_concurrency.py::test_concurrent_commands_on_one_timer_stay_consistent` |
| I-7 | A retried request never applies twice | `Idempotency-Key` required on all timer commands and manual create; key + exact response bytes stored in the **same transaction** as the mutation; concurrent duplicates wait on the key's primary key and replay; the client-generated entry ID makes `start` idempotent even without the key | `test_idempotency.py::*`, `test_timer_concurrency.py::test_concurrent_duplicates_with_the_same_key_are_one_request`, `::test_concurrent_retries_with_the_same_entry_id_and_new_keys` |
| I-8 | The hourly rate is snapshotted when an entry is created and never changes implicitly | `hourly_rate_snapshot`, `currency`, `rate_source` set on start / manual create; edits recompute with the same snapshot; only `reprice: true` re-resolves it and stamps `rate_corrected_at` | `test_timer.py::TestRates::test_snapshot_is_immutable_when_project_rate_changes`, `test_time_entries.py::TestEdit::test_reprice_is_an_explicit_correction` |
| I-9 | Money is exact | `Decimal` + `NUMERIC(10,2)` / `NUMERIC(14,2)`; `amount = round_half_up(seconds × rate / 3600, 0.01)`; totals = sums of per-entry amounts; JSON money as strings | `tests/unit/test_timekeeping.py::test_amount_vectors`, `test_time_entries.py::TestHistory::test_pagination_filters_and_summary` |
| I-10 | Concurrent edits do not overwrite each other | `version` on every entry, incremented by each change; `PATCH` requires the current `version`, else `409 VERSION_CONFLICT` with the current entry; row lock while editing | `test_time_entries.py::TestEdit::test_optimistic_locking` |
| I-11 | A manual entry is at most 24 **real** hours | Service check + `CHECK (ended_at - started_at <= interval '24 hours')` on `TIMESTAMPTZ` (so a 25-hour DST day is rejected) | `test_timezones.py::TestDaylightSaving::test_24h_manual_limit_uses_real_hours` |
| I-12 | Entries cannot end in the future | `ended_at ≤ now + 60 s` | `test_time_entries.py::TestManual::test_validation` |
| I-13 | Ownership: entries, projects and tasks of other users are invisible | All queries filtered by `user_id` (404 for foreign IDs); composite FKs `(project_id, user_id)`, `(task_id, user_id)` | `test_timer.py::TestInvariants::test_other_users_entry_is_not_found`, `::test_other_users_project_or_task` |
| I-14 | History is never silently lost | Project with entries cannot be deleted (`409 RESOURCE_IN_USE`, FK `RESTRICT`); deleting a task keeps its entries (`ON DELETE SET NULL (task_id)`); archived projects reject new time (`409 PROJECT_ARCHIVED`) | `test_time_entries.py::TestDeleteAndRelations::*`, `test_timer.py::TestInvariants::test_archived_project_cannot_be_tracked` |
| I-15 | Stopped entries are internally consistent | CHECKs: `stopped ⇔ ended_at`, `stopped ⇔ duration_seconds`, `ended_at > started_at`, `manual ⇒ stopped`, non-negative duration/amount; pauses outside a new range are clipped on edit | `test_time_entries.py::TestEdit::test_editing_times_clips_pauses`, `test_timer_concurrency.py::test_concurrent_commands_on_one_timer_stay_consistent` |

## 4. Retries and idempotency in detail

1. The client sends `Idempotency-Key: <uuid>` (8–100 chars `[A-Za-z0-9_-:.]`). Missing → `428 IDEMPOTENCY_KEY_REQUIRED`.
2. In one transaction: `INSERT … ON CONFLICT DO NOTHING` claims the key → the command runs → the exact response
   bytes are written to the key row → `COMMIT`.
3. A concurrent copy of the same request blocks on the key's primary key until the first commits, then **replays**
   the stored status and body (`Idempotent-Replayed: true`). The body is stored as `TEXT`, not `JSONB`, because JSONB
   reorders keys and replays must be byte-identical.
4. Same key with a different payload or endpoint → `422 IDEMPOTENCY_KEY_REUSED`.
5. **Errors are not cached.** A failing command rolls back, key included, so the retry runs again (for example after
   the user stopped the conflicting timer).
6. Keys are per user and kept 48 hours; expired keys are purged by the user's next successful command.
7. `POST /timer/start` also carries a client-generated entry `id`: if the key was lost, a repeated start with the
   same `id` returns the existing entry with `200` instead of creating a second one.

## 5. Time zones, midnight and daylight saving

- Storage and arithmetic: UTC instants only. A timer from 02:30 to 03:30 local on the night clocks go back
  (Europe/Kyiv, 25 Oct 2026) lasts **2 h** and is billed as 2 h; across the spring-forward gap
  (29 Mar 2026, 02:30 → 04:30 local) it lasts **1 h**.
- Ambiguous wall times must carry an offset (`03:30+03:00` vs `03:30+02:00`); naive timestamps are rejected.
- Grouping and filters use the user's IANA time zone (`users.timezone`): `from`/`to` are local calendar dates
  (inclusive), converted to `[local midnight of from, local midnight after to)` in UTC with `zoneinfo`, so a
  25-hour or 23-hour day is covered exactly. `days[]` groups by the local date of `started_at`.
- An entry crossing midnight belongs to the day it **started** (assumption A-8); its duration is not split.
- Changing the user's time zone re-groups history but never changes a duration or an amount.

## 6. Restarts and failures

- An active timer is just a row with `started_at` and pauses, so a server restart, crash or deploy loses
  nothing: `GET /timer/current` after restart returns the same entry with `elapsed_seconds` computed from the stored
  instants and the current `server_time`. Downtime while running counts (the user was working); downtime while
  paused does not. Proven by `test_timer_concurrency.py::TestRestart`.
- Every response includes `server_time`; clients compute the live display as
  `elapsed_seconds + (device_now + offset − server_time)` and never persist a counter.
- A command that fails mid-way leaves no trace: the transaction (including the idempotency key) rolls back.

## 7. Lessons captured by the tests

Two real defects were found by the concurrency tests during implementation and are now guarded:

1. **Deadlock between the per-user lock and foreign keys.** Inserting an idempotency key or an entry takes
   `FOR KEY SHARE` on the user row; serialising with `FOR UPDATE` then deadlocked two concurrent requests.
   The lock is `FOR NO KEY UPDATE`, which serialises commands without conflicting with FK checks.
2. **Clock read before the lock.** A command that waited for the lock carried a timestamp older than the command
   that held it and was rejected as out of order. The service now reads the clock after taking the lock.

## 8. Deferred

- `invoice_id` and `ENTRY_LOCKED` (editing invoiced entries) arrive with invoices (Phase 8).
- Billing increments (rounding time to 6/15 minutes) are not implemented (open question Q-2).
