from collections.abc import Iterator
from functools import lru_cache

from sqlalchemy import Engine, create_engine
from sqlalchemy.orm import Session, sessionmaker

from app.core.config import get_settings


@lru_cache
def get_engine() -> Engine:
    settings = get_settings()
    return create_engine(
        str(settings.database_url),
        pool_size=settings.db_pool_size,
        pool_pre_ping=True,
        echo=settings.db_echo,
        # Session time zone UTC: timestamps come back as aware UTC datetimes regardless of server config.
        connect_args={"options": "-c timezone=UTC"},
    )


@lru_cache
def get_session_factory() -> sessionmaker[Session]:
    return sessionmaker(bind=get_engine(), autoflush=False, expire_on_commit=False)


def get_db() -> Iterator[Session]:
    """One session per request. Services commit explicitly; anything uncommitted is rolled back."""
    session = get_session_factory()()
    try:
        yield session
    finally:
        session.close()
