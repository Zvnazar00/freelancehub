"""Real concurrency: these tests commit for real (no rollback wrapper) and race threads against Postgres."""

import threading
import uuid
from collections.abc import Callable, Iterator
from typing import Any

import pytest
from sqlalchemy import Engine, func, select, text
from sqlalchemy.orm import Session, sessionmaker

from app.core.config import Settings
from app.core.errors import Unauthorized
from app.models import Client, Project, RefreshToken, Task, User
from app.schemas.auth import RegisterRequest
from app.schemas.tasks import TaskCreate
from app.services import auth as auth_service
from app.services import tasks as task_service


@pytest.fixture
def session_factory(engine: Engine) -> Iterator[sessionmaker[Session]]:
    yield sessionmaker(bind=engine, expire_on_commit=False)
    with engine.begin() as conn:  # clean up committed rows
        conn.execute(text("TRUNCATE users CASCADE"))


def race(n: int, fn: Callable[[], Any]) -> list[Any]:
    barrier = threading.Barrier(n)
    results: list[Any] = [None] * n

    def worker(i: int) -> None:
        barrier.wait()
        try:
            results[i] = fn()
        except Exception as exc:  # collected for assertions
            results[i] = exc

    threads = [threading.Thread(target=worker, args=(i,)) for i in range(n)]
    for t in threads:
        t.start()
    for t in threads:
        t.join(timeout=30)
    return results


def test_parallel_refresh_with_same_token_rotates_exactly_once(
    session_factory: sessionmaker[Session], settings: Settings
) -> None:
    with session_factory() as s:
        issued = auth_service.register(
            s, RegisterRequest(email="race@example.com", password="race-password-1", full_name="R"), settings, None
        )

    def attempt() -> Any:
        with session_factory() as s:
            return auth_service.refresh(s, issued.refresh_token, settings, None)

    results = race(4, attempt)
    successes = [r for r in results if isinstance(r, auth_service.IssuedTokens)]
    failures = [r for r in results if isinstance(r, Unauthorized)]
    assert len(successes) == 1, results
    assert len(failures) == 3 and all(f.code == "TOKEN_ROTATED" for f in failures)
    with session_factory() as s:
        assert s.scalar(select(func.count()).select_from(RefreshToken)) == 2  # original + one rotation


def test_parallel_task_creation_gets_unique_positions(
    session_factory: sessionmaker[Session], settings: Settings
) -> None:
    with session_factory() as s:
        issued = auth_service.register(
            s, RegisterRequest(email="tasks@example.com", password="race-password-1", full_name="T"), settings, None
        )
        user_id = issued.user.id
        client = Client(user_id=user_id, name="C", currency="USD")
        s.add(client)
        s.flush()
        project = Project(user_id=user_id, client_id=client.id, name="P", currency="USD")
        s.add(project)
        s.commit()
        project_id = project.id

    def create() -> Any:
        with session_factory() as s:
            user = s.get(User, user_id)
            assert user is not None
            return task_service.create_task(s, user, TaskCreate(project_id=project_id, title=f"t-{uuid.uuid4()}"))

    results = race(6, create)
    assert not [r for r in results if isinstance(r, Exception)], results
    with session_factory() as s:
        positions = sorted(s.scalars(select(Task.position).where(Task.project_id == project_id)))
    assert positions == list(range(6))
