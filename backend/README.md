# FreelanceHub — Backend

FastAPI · SQLAlchemy 2.1 · Alembic · PostgreSQL 16 · Pydantic v2 · Python 3.13

Implements Phases 1–4 and 6–8 of `docs/roadmap.md`: authentication, profile, ownership-protected clients / projects /
tasks, the time-tracking engine, dashboard and analytics, CSV exports, invoices with payments, and invoice PDFs
(fpdf2 — pure Python, the Inter font is bundled in `app/assets/fonts`, so the image needs no system libraries).

## Run with Docker (recommended)

```bash
cp .env.example .env          # from the repository root; set POSTGRES_PASSWORD and JWT_SECRET
docker compose up --build     # API on http://localhost:8000, docs at /docs
docker compose exec api pytest
```

The API container runs `alembic upgrade head` before starting.

## Run locally (without Docker)

```bash
cd backend
python -m venv .venv && source .venv/bin/activate      # Windows: .venv\Scripts\activate
pip install -e ".[dev]"
export DATABASE_URL=postgresql+psycopg://user:pass@localhost:5432/freelancehub
export JWT_SECRET=$(python -c "import secrets; print(secrets.token_urlsafe(48))")
alembic upgrade head
uvicorn app.main:app --reload
```

## Quality checks

```bash
ruff check . && ruff format --check .
mypy                       # strict
pytest --cov               # needs PostgreSQL; set TEST_DATABASE_URL (default: postgres@localhost/freelancehub_test)
```

**Tests never touch your dev data:** they drop and recreate a separate `*_test` database, migrate it with Alembic,
and run each test inside a rolled-back transaction. Concurrency tests commit for real and truncate afterwards.

## Layout

```
app/
├── main.py              # app factory, request-ID + logging middleware
├── core/                # settings, security (Argon2id, JWT), errors, rate limiting, pagination, logging
├── db/                  # declarative base (naming conventions), engine/session
├── models/              # SQLAlchemy models (composite ownership FKs)
├── schemas/             # Pydantic request/response models (money = decimal strings)
├── repositories/        # queries — always scoped by user_id
├── services/            # business rules and transactions (money.py = the only place money is rounded)
└── api/v1/              # routers (/api/v1/...), dependencies, RFC 9457 error handlers
alembic/versions/        # 0001 users+auth, 0002 clients+projects, 0003 tasks, 0004 time entries, 0005 invoices+payments
tests/unit, tests/integration
```

## Demo data

```bash
docker compose exec api python -m app.cli.seed_demo   # demo@freelancehub.app / FreelanceHub-demo-2026
```

Recreates only the demo user: 4 clients, 7 projects, ~160 entries, invoices in every state, a running timer.

## Money

All amounts are `Decimal` / `NUMERIC`, serialised as strings with an explicit currency, rounded half-up to cents in
`services/money.py`. Totals are sums of already-rounded lines; tax is computed once on the subtotal. Dashboards keep
**tracked**, **invoiced** and **received** separate and never add currencies. See `docs/architecture.md` §8.

## Security notes

- Passwords: Argon2id. Access tokens: HS256 JWT, 15 min, carry `sub` (user) and `sid` (session family).
- Refresh tokens: opaque 256-bit, stored as SHA-256 only, rotated on every use. Reusing a rotated token
  revokes the whole session (after a 10 s grace window for network retries → `TOKEN_ROTATED`).
- Every query is filtered by the authenticated user; foreign IDs return `404`. Composite foreign keys
  `(parent_id, user_id)` make cross-user links impossible even at the SQL level.
- Unknown request fields (e.g. `user_id`) are rejected with `422`.
- Logs are JSON with request IDs; passwords and tokens are redacted and request bodies are never logged.
- Rate limiting is in-process (single instance); move to Redis before running several replicas.
