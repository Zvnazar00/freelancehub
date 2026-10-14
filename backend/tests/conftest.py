"""Test harness.

* A dedicated database (`<name>_test`) is dropped, recreated and migrated with Alembic once per run,
  so tests exercise the real schema: partial indexes, composite FKs, CHECKs, row locks.
* Each test runs inside an outer transaction that is rolled back; service-level commits only release
  SAVEPOINTs (join_transaction_mode="create_savepoint"). Tests are isolated and order-independent.
"""

import os
from collections.abc import Iterator
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any

import pytest
from sqlalchemy import Engine, create_engine, text
from sqlalchemy.engine import make_url
from sqlalchemy.orm import Session

TEST_DATABASE_URL = os.environ.get(
    "TEST_DATABASE_URL", "postgresql+psycopg://postgres@localhost:5432/freelancehub_test"
)
os.environ.update(
    ENVIRONMENT="test",
    DATABASE_URL=TEST_DATABASE_URL,
    JWT_SECRET="test-secret-that-is-long-enough-for-hs256-0123456789",
    LOG_LEVEL="WARNING",
)

from alembic.config import Config  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from alembic import command  # noqa: E402
from app.core.clock import get_clock  # noqa: E402
from app.core.config import Settings, get_settings  # noqa: E402
from app.db.session import get_db  # noqa: E402
from app.main import create_app  # noqa: E402

BACKEND_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def alembic_config(url: str) -> Config:
    cfg = Config(os.path.join(BACKEND_DIR, "alembic.ini"))
    cfg.set_main_option("script_location", os.path.join(BACKEND_DIR, "alembic"))
    cfg.attributes["database_url"] = url
    cfg.attributes["configure_logger"] = False
    return cfg


def recreate_database(url: str) -> None:
    parsed = make_url(url)
    admin = create_engine(parsed.set(database="postgres"), isolation_level="AUTOCOMMIT")
    with admin.connect() as conn:
        conn.execute(text(f'DROP DATABASE IF EXISTS "{parsed.database}" WITH (FORCE)'))
        conn.execute(text(f'CREATE DATABASE "{parsed.database}"'))
    admin.dispose()


@pytest.fixture(scope="session")
def engine() -> Iterator[Engine]:
    recreate_database(TEST_DATABASE_URL)
    command.upgrade(alembic_config(TEST_DATABASE_URL), "head")
    eng = create_engine(TEST_DATABASE_URL, connect_args={"options": "-c timezone=UTC"})
    yield eng
    eng.dispose()


@pytest.fixture
def settings() -> Settings:
    return Settings(
        environment="test",
        database_url=TEST_DATABASE_URL,  # type: ignore[arg-type]
        jwt_secret="test-secret-that-is-long-enough-for-hs256-0123456789",  # type: ignore[arg-type]
        login_rate_limit=1000,
        register_rate_limit=1000,
    )


@pytest.fixture
def db(engine: Engine) -> Iterator[Session]:
    connection = engine.connect()
    outer = connection.begin()
    session = Session(bind=connection, join_transaction_mode="create_savepoint", expire_on_commit=False)
    try:
        yield session
    finally:
        session.close()
        outer.rollback()
        connection.close()


class FakeClock:
    """Controllable UTC clock injected into the API (get_clock). Time only moves when a test says so."""

    def __init__(self, now: datetime) -> None:
        self.now = now

    def __call__(self) -> datetime:
        return self.now

    def advance(self, **delta: float) -> datetime:
        self.now += timedelta(**delta)
        return self.now

    def set(self, value: datetime) -> datetime:
        self.now = value.astimezone(UTC)
        return self.now


@pytest.fixture
def clock() -> FakeClock:
    return FakeClock(datetime(2026, 10, 12, 10, 0, 0, tzinfo=UTC))


@pytest.fixture
def app(db: Session, settings: Settings, clock: FakeClock) -> Any:
    application = create_app(settings)
    application.dependency_overrides[get_db] = lambda: db
    application.dependency_overrides[get_settings] = lambda: settings
    application.dependency_overrides[get_clock] = lambda: clock
    return application


@pytest.fixture
def client(app: Any) -> Iterator[TestClient]:
    with TestClient(app) as c:
        yield c


@dataclass
class AuthedUser:
    id: str
    email: str
    password: str
    access_token: str
    refresh_token: str

    @property
    def headers(self) -> dict[str, str]:
        return {"Authorization": f"Bearer {self.access_token}"}


def register(client: TestClient, email: str, password: str = "correct-horse-battery", **extra: Any) -> AuthedUser:
    payload = {"email": email, "password": password, "full_name": "Test User", **extra}
    response = client.post("/api/v1/auth/register", json=payload)
    assert response.status_code == 201, response.text
    body = response.json()
    return AuthedUser(body["user"]["id"], email, password, body["access_token"], body["refresh_token"])


@pytest.fixture
def alice(client: TestClient) -> AuthedUser:
    return register(client, "alice@example.com")


@pytest.fixture
def bob(client: TestClient) -> AuthedUser:
    return register(client, "bob@example.com")
