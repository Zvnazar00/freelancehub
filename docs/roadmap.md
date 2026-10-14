# FreelanceHub — Roadmap

> Status: **v0.5.** Each phase is a vertical slice (API + DB + mobile UI + tests) and ends with a report:
> files changed, commands run, test results, and remaining risks. A phase is done only when it meets the
> *Definition of done* in [CONTRIBUTING.md](../CONTRIBUTING.md).

## Phase overview

| Phase | Scope | Exit criteria (summary) |
|-------|-------|-------------------------|
| 0 | Foundations | `docker compose up` runs API + DB, CI green, Expo app boots with theme |
| 1 | Authentication — **done** (API + mobile) | Register/login/refresh/logout end-to-end, token rotation and reuse tests |
| 2 | Clients & projects — **done** (API + mobile list/detail/create; edit/archive UI pending) | CRUD + archive with ownership tests, mobile list/detail/forms |
| 3 | Tasks — **done** (API + mobile quick-add/toggle; edit sheet pending) | CRUD, status, reorder, project detail screen |
| 4 | **Timer core** — **done** except the persisted offline queue | State machine, invariants, idempotency, offline queue, restart restore |
| 5 | Manual entries & history | Manual create, edit/delete with version, entries list, overlap UX |
| 6 | Earnings & dashboard — **done** (API + mobile) | Money service, dashboard, analytics charts, TZ bucketing |
| 7 | CSV export — **done** (time entries + invoices; share sheet on mobile, download on web) | CSV, share sheet on mobile |
| 8 | Invoices, payments, PDF — **done** | Draft → sent → paid/void, entry locking, PDF |
| 9 | Hardening & portfolio polish | Password reset, a11y pass, demo seed, README, screenshots, deploy |

## Phase 0 — Foundations

**Status (2026-10-12): mobile foundation done; backend, Docker and CI not started.**
Done: Expo SDK 57 app in `mobile/` (Expo Router, strict TS), Dark Developer design system + gallery screen,
navigation with 5 tabs + detail/modal screens, timer state machine and money helpers (unit-tested),
temporary demo data clearly separated in `mobile/src/demo/`. Verified: `tsc`, `eslint`, 71 Jest tests,
Android Hermes bundle export, web export rendered in headless Chromium.
Remaining for Phase 0: GitHub Actions, root README.

**Status (2026-10-12): backend for Phases 1–3 done** (`backend/`): FastAPI + SQLAlchemy 2.1 + Alembic (3 reversible
migrations), Argon2id + JWT + rotating refresh tokens with reuse detection, profile, ownership-protected CRUD for
clients / projects / tasks, RFC 9457 errors, JSON logs with request IDs, Docker Compose. Verified: 101 pytest tests on
PostgreSQL 16 (97 % coverage, incl. cross-user matrix, real-concurrency races, migration round-trip and model/migration
sync), ruff, mypy --strict, live HTTP smoke test. Not verified: `docker compose up` (image registry unreachable from the
build environment). Mobile screens for Phases 1–3 still use demo data — wiring them to the API is the next step.

- Monorepo skeleton per [architecture.md §4](architecture.md). `.gitignore`, `.env.example`, `README.md`.
- Backend: FastAPI app factory, settings, structured logging with redaction, Problem Details handler, `/health`, SQLAlchemy session, Alembic init with naming conventions, pytest config with a Postgres test DB.
- `docker-compose.yml`: `db` (postgres:16), `api` (uvicorn reload in dev), healthchecks.
- Mobile: Expo (latest stable SDK, verified at scaffold time) + Expo Router + TS strict, ESLint, Prettier, Jest; theme tokens; base UI kit (Screen, Text, Button, Card, Input, EmptyState, ErrorState, Skeleton); API client with typed errors.
- CI: `backend.yml` (ruff, mypy, pytest, migration round-trip); `mobile.yml` (tsc, eslint, jest).
- **Done when**: CI is green on a clean clone and the app shows a themed placeholder screen calling `/health`.

## Mobile ↔ API integration

**Status (2026-10-12): done.** The demo store is gone; every screen reads the real API.
- `shared/api`: typed fetch client, RFC 9457 → `ApiError`, single-flight refresh, reachability, query-key factory.
- Auth: sign-in / sign-up (RHF + Zod, server field errors mapped back), `Stack.Protected` guard, session restore
  during the splash, offline start from the cached profile, sign-out / sign-out everywhere.
- Tokens: refresh token only in SecureStore (memory-only on web), access token only in memory.
- Timer: optimistic commands with idempotent retries, server-clock offset, persisted snapshot → restored after
  backgrounding and app restarts; elapsed time always derived from timestamps.
- New screens: New project (client/billing/rate/budget/colour), task quick-add and toggle, Settings with real profile,
  week start / time zone via `PATCH /me`, connection info.
- Backend additions: `tracked_seconds` and per-currency `unbilled` in project/client `stats` (one grouped query),
  legacy time-zone aliases (`Europe/Kiev` → `Europe/Kyiv`), CORS exposes `X-Request-ID`.
- Client-generated entry IDs and Idempotency-Keys come from the platform CSPRNG (`expo-crypto`), not `Math.random`.
- Verified (re-run 2026-10-12): backend 193 pytest, ruff, mypy --strict; mobile `tsc`, `eslint`, 118 Jest tests,
  Android Hermes export; **`scripts/e2e/web_e2e.py`** — Playwright on the web build against a live FastAPI +
  PostgreSQL, 25/25 checks in 3 consecutive runs: sign-up/sign-in validation (client and server), client and project
  forms, start → pause → resume → stop with database verification of status, pause intervals, rate snapshot,
  duration and amount; 6 s of frozen JS (simulated backgrounding) with elapsed time matching the stored timestamps;
  failed command rolled back; access-token expiry handled by exactly one shared refresh; timer restored from the
  server after reload; no tokens in local/session storage, cookies or IndexedDB; sign-out revokes the session.
- Not verified here: a physical phone (SecureStore on a real Keychain/Keystore, real OS backgrounding).
- Remaining: persisted offline command queue + two-device conflict sheet, edit/archive screens, manual entries UI.

## Phase 1 — Authentication
- Migration `0001`; Argon2id; JWT access; refresh rotation with family revocation and 10 s grace; rate limiting; `/me`.
- Mobile: sign-in/sign-up forms (RHF + Zod), SecureStore, single-flight refresh, protected route group, splash during bootstrap, sign-out.
- Tests: happy paths, wrong password, duplicate email, expired/forged/wrong-type JWT, refresh reuse → family revoked, logout-all, no tokens in logs.

## Phase 2 — Clients & projects
- Migrations `0002`; composite FKs; archive/unarchive; `RESOURCE_IN_USE` rules; rate fields with Decimal validation.
- Mobile: Clients tab, Projects tab with filters, detail screens, create/edit modals, empty/error/loading states.
- Tests: CRUD, validation, **cross-user read/update/delete/link → 404** for every endpoint.

## Phase 3 — Tasks
- Migration `0003`; CRUD; reorder; `completed_at` handling.
- Mobile: task list in the project detail, quick-add, status toggle, edit sheet.

## Phase 4 — Timer core (highest priority for quality)

**Status (2026-10-12): backend done** — migration `0004`, timer + manual entries + edit/delete + history API,
idempotency, per-user serialisation; 188 pytest tests incl. real-concurrency races, restarts, midnight and DST.
Invariants and their proofs: [time-tracking.md](time-tracking.md). Mobile wiring (queue, clock offset) is next.

- Migration `0004` (entries, pauses, idempotency keys, partial unique index, exclusion constraint).
- Services: rate resolution, `at` validation, transitions under `FOR UPDATE`, duration/amount on stop.
- Idempotency dependency (same-transaction storage, replay, hash mismatch).
- Mobile: Time tab big timer, MiniTimerBar, project/task picker, server-offset clock, persisted command queue with ordered replay, AppState refetch, conflict sheet, long-running banner.
- Tests:
  - Unit: every transition (valid/invalid), pause arithmetic, rounding vectors.
  - Integration: double start → 409; concurrent stops (threads) → exactly one transition; replay of the same key → identical response; key reuse with a different body → 422; command to a non-active entry → `TIMER_MISMATCH`; `at` future/out-of-order; stop while paused closes the pause.
  - Mobile: elapsed calc with pauses and offset; queue replay order and stop-on-4xx.
- Manual QA script: start → kill app → reopen (restored); airplane mode start/pause/stop → reconnect (synced, no dupes); two devices conflict.

## Phase 5 — Manual entries & history
- Manual create (24 h cap, overlap → `TIME_OVERLAP` with the conflicting entry), PATCH with `version`, `reprice`, pause clipping on edit, delete.
- Mobile: entries list grouped by day with daily totals, filters, edit modal, version-conflict handling (refetch + re-apply).

## Phase 6 — Earnings, dashboard, analytics — done
- Backend: `services/money.py` (Decimal, half-up, unit-tested against the reference vectors), `/dashboard/summary`,
  `/analytics/timeseries`, `/analytics/breakdown`, `/projects/{id}/summary`. Local-date ranges with DST and `week_start` tests.
- Mobile: Dashboard with one card per currency showing **tracked / invoiced / received** side by side, balances
  (unbilled · outstanding · overdue), period bar (week/month/quarter/year with previous/next navigation → explicit `from`/`to` dates), activity chart,
  top projects; Analytics screen (breakdown by project or client, effective hourly rate); project economics card.
- Charts are plain `View`s (bars with accessible summaries) instead of a chart library: no native dependency, works in Expo Go.

## Phase 7 — CSV export — done
- `/exports/time-entries.csv` and `/exports/invoices.csv`: UTF-8 BOM, formula-injection guard, user TZ, max one year.
- Mobile: bytes fetched through the authenticated client, written with `expo-file-system`, shared with `expo-sharing`
  (web: a regular browser download).

## Phase 8 — Invoices, payments, PDF — done
- Migration `0005`; numbering `INV-YYYY-NNNN` assigned on send under the per-user lock (no gaps/dupes, concurrency-tested);
  draft/send/void/payment rules; entries locked while on an invoice; dashboard invoiced/received/outstanding are real.
- PDF with **fpdf2** (pure Python, bundled Inter font with Cyrillic) instead of WeasyPrint: no system libraries in the image.
- Mobile: invoices list with status filter, create from unbilled entries (+ custom lines, tax, live preview with the server's
  rounding rules), detail with two-tap send, record/delete payment, void, delete draft, share PDF.
- Edit draft (`/invoices/edit/[id]`): the same form as "New invoice", opened with the draft's entries selected and its
  custom lines, dates, tax and notes restored; `PATCH` carries the version, a conflict offers "Load latest version"
  instead of overwriting; unticked entries are released by the server.
- Verified: backend pytest (273), mobile Jest (149), `scripts/e2e/finance_e2e.py` 29/29 on a real API + PostgreSQL.
- Pending: sending invoices by email.

## Phase 9 — Hardening & portfolio polish
- Password reset via email (provider TBD), account deletion.
- Accessibility pass (labels, dynamic type, contrast), haptics, micro-animations.
- Done: demo seed (`app/cli/seed_demo.py`), root README with architecture diagram and screenshots.
- Pending: screencast/GIF, deploy (API + managed Postgres; EAS build for mobile).

## Open questions (decisions with defaults)

| # | Question | Default if not answered |
|---|----------|-------------------------|
| Q-1 | Allow overlapping entries? | **No** (DB exclusion constraint) |
| Q-2 | Billing increments (round to 6/15 min)? | **No** in MVP, exact seconds |
| Q-3 | Sync vs async SQLAlchemy? | **Sync** (ADR-03) |
| Q-4 | Which currencies? | 2-decimal list in A-4, no FX |
| Q-5 | Where to deploy the demo API? | Decide in Phase 9 (any container host + managed Postgres) |
| Q-6 | Password reset email provider? | Decide in Phase 9 |
| Q-7 | Do we need local notifications for running timers? | Post-MVP |
