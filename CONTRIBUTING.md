# Contributing to FreelanceHub

Conventions this codebase follows. Read the design documents first:
[architecture](docs/architecture.md) · [database](docs/database.md) · [API](docs/api.md) ·
[time tracking](docs/time-tracking.md) · [roadmap](docs/roadmap.md). Keep them in sync with the code.

## Architecture

- The mobile app (`mobile/`) and the API (`backend/`) are separate projects.
- Mobile code is organised by feature (`src/features/<feature>`); route files in `src/app` stay thin and business
  rules stay out of components.
- Backend layers: routes → services (business rules, transactions) → repositories (queries, always scoped by user).
- Request and response contracts are typed on both sides; inputs are validated on the client and on the server.
- Every database migration is reversible.
- No abstraction or optimisation before there is a need for it.

## Time tracking

- At most one active (running or paused) entry per user, enforced by the database.
- Elapsed time is always derived from stored timestamps, never from an incrementing counter.
- Paused intervals are excluded from billable time; each entry keeps a snapshot of its hourly rate.
- Commands are idempotent (`Idempotency-Key` + client-generated IDs); the active timer is restored after a restart.
- Consistency guarantees and concurrency controls are documented in [time-tracking.md](docs/time-tracking.md).

## Money

- `Decimal` in Python and `NUMERIC` in PostgreSQL; never floats for authoritative amounts.
- Currency is always stored explicitly; amounts in different currencies are never added together.
- Rounding rules live in one module (`backend/app/services/money.py`) and are covered by tests.
- Historical entry rates are immutable unless the explicit correction flow (`reprice`) is used.
- Tracked value, invoiced amounts and received payments are separate concepts in the API and the UI.

## Security

- Every protected resource is filtered by the authenticated user; client-supplied user IDs are never trusted.
- Passwords are hashed with Argon2id; access tokens are short-lived, refresh tokens rotate.
- Secrets come from environment variables; real credentials are never committed.
- Cross-user access and unauthorised operations have tests.
- Logs never contain passwords, tokens or request bodies.

## UI

- Dark design system in `mobile/src/shared/theme` and `mobile/src/shared/ui`; reuse its components and tokens.
- Every data screen has loading, empty, error and success states; controls have accessible labels and touch targets.
- No hard-coded user-facing text: add the key to `en.ts`, `uk.ts` and `ru.ts` in the same change.
- Dates, numbers, durations and money are formatted only through `shared/lib/time.ts` and `shared/lib/money.ts`.

## Before a change is done

1. The feature works end to end: UI, API, persistence, validation, authorisation and error handling.
2. Tests cover it, including error and edge cases.
3. Checks pass:
   - backend: `ruff check . && ruff format --check . && mypy && pytest`
   - mobile: `npm run check` (type check, lint, tests)
4. Documentation is updated.
