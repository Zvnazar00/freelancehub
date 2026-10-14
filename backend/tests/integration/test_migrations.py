"""Migrations are reversible and match the ORM models exactly."""

from collections.abc import Iterator

import pytest
from alembic.autogenerate import compare_metadata
from alembic.migration import MigrationContext
from sqlalchemy import create_engine, text
from sqlalchemy.engine import make_url

import app.models  # noqa: F401
from alembic import command
from app.db.base import Base
from tests.conftest import TEST_DATABASE_URL, alembic_config, recreate_database

MIGRATIONS_URL = (
    make_url(TEST_DATABASE_URL).set(database="freelancehub_migrations").render_as_string(hide_password=False)
)


@pytest.fixture
def scratch_db() -> Iterator[str]:
    recreate_database(MIGRATIONS_URL)
    yield MIGRATIONS_URL
    admin = create_engine(make_url(MIGRATIONS_URL).set(database="postgres"), isolation_level="AUTOCOMMIT")
    with admin.connect() as conn:
        conn.execute(text('DROP DATABASE IF EXISTS "freelancehub_migrations" WITH (FORCE)'))
    admin.dispose()


def _schema_objects(url: str) -> tuple[set[str], set[str]]:
    engine = create_engine(url)
    with engine.connect() as conn:
        tables = set(conn.scalars(text("SELECT tablename FROM pg_tables WHERE schemaname = 'public'")))
        enums = set(conn.scalars(text("SELECT typname FROM pg_type WHERE typtype = 'e'")))
    engine.dispose()
    return tables, enums


def test_upgrade_downgrade_upgrade_round_trip(scratch_db: str) -> None:
    cfg = alembic_config(scratch_db)
    command.upgrade(cfg, "head")
    tables, enums = _schema_objects(scratch_db)
    assert {
        "users",
        "refresh_tokens",
        "clients",
        "projects",
        "tasks",
        "time_entries",
        "time_entry_pauses",
        "idempotency_keys",
        "invoices",
        "invoice_items",
        "payments",
    } <= tables
    assert enums == {
        "project_status",
        "billing_type",
        "task_status",
        "task_priority",
        "time_entry_status",
        "entry_source",
        "rate_source",
        "invoice_status",
        "invoice_item_kind",
        "payment_method",
    }

    command.downgrade(cfg, "base")
    tables, enums = _schema_objects(scratch_db)
    assert tables == {"alembic_version"} and enums == set()

    command.upgrade(cfg, "head")
    assert _schema_objects(scratch_db)[0] >= {"users", "tasks"}


def test_models_and_migrations_are_in_sync(scratch_db: str) -> None:
    command.upgrade(alembic_config(scratch_db), "head")
    engine = create_engine(scratch_db)
    with engine.connect() as conn:
        diff = compare_metadata(MigrationContext.configure(conn, opts={"compare_type": True}), Base.metadata)
    engine.dispose()
    assert diff == [], f"Models differ from migrations: {diff}"
