import uuid
from datetime import UTC, date, datetime

from sqlalchemy.orm import Session

from app.core.errors import AppError, NotFound, ValidationFailed
from app.core.pagination import cursor_uuid, decode_cursor, encode_cursor
from app.models import Task, User
from app.models.enums import TaskStatus
from app.repositories import projects as projects_repo
from app.repositories import tasks as repo
from app.schemas.common import Page
from app.schemas.tasks import TaskCreate, TaskOut, TaskReorder, TaskUpdate


def _get(db: Session, user: User, task_id: uuid.UUID) -> Task:
    task = repo.get_task(db, user.id, task_id)
    if task is None:
        raise NotFound("Task not found.")
    return task


def _lock_project(db: Session, user: User, project_id: uuid.UUID) -> None:
    """Locks the parent project row so concurrent creates/reorders get consistent positions."""
    if projects_repo.get_project(db, user.id, project_id, for_update=True) is None:
        raise NotFound("Project not found.")


def _apply_status(task: Task, status: TaskStatus) -> None:
    if status is TaskStatus.done and task.completed_at is None:
        task.completed_at = datetime.now(UTC)
    elif status is not TaskStatus.done:
        task.completed_at = None
    task.status = status


def list_tasks(
    db: Session,
    user: User,
    *,
    project_id: uuid.UUID | None,
    status: TaskStatus | None,
    due_before: date | None,
    cursor: str | None,
    limit: int,
) -> Page[TaskOut]:
    if project_id and projects_repo.get_project(db, user.id, project_id) is None:
        raise NotFound("Project not found.")
    after = None
    if cursor:
        key, raw_id = decode_cursor(cursor, 2)
        after = (key, cursor_uuid(raw_id))
    try:
        rows = repo.list_tasks(
            db, user.id, project_id=project_id, status=status, due_before=due_before, after=after, limit=limit + 1
        )
    except ValueError as exc:  # cursor key not matching the ordering
        raise AppError("Malformed cursor.", code="BAD_REQUEST") from exc
    page, has_more = rows[:limit], len(rows) > limit
    next_cursor = None
    if has_more and page:
        last = page[-1]
        key_value = last.position if project_id else (last.due_date or repo.FAR_FUTURE).isoformat()
        next_cursor = encode_cursor([key_value, last.id])
    return Page[TaskOut](items=[TaskOut.model_validate(t) for t in page], next_cursor=next_cursor)


def get_task(db: Session, user: User, task_id: uuid.UUID) -> TaskOut:
    return TaskOut.model_validate(_get(db, user, task_id))


def create_task(db: Session, user: User, data: TaskCreate) -> TaskOut:
    _lock_project(db, user, data.project_id)
    task = Task(
        user_id=user.id,
        project_id=data.project_id,
        title=data.title,
        description=data.description or None,
        priority=data.priority,
        due_date=data.due_date,
        estimate_minutes=data.estimate_minutes,
        position=repo.next_position(db, data.project_id),
    )
    _apply_status(task, data.status)
    db.add(task)
    db.commit()
    db.refresh(task)
    return TaskOut.model_validate(task)


def update_task(db: Session, user: User, task_id: uuid.UUID, data: TaskUpdate) -> TaskOut:
    task = _get(db, user, task_id)
    changes = data.model_dump(exclude_unset=True)
    status = changes.pop("status", None)
    for field, value in changes.items():
        setattr(task, field, value)
    if status is not None:
        _apply_status(task, status)
    db.commit()
    db.refresh(task)
    return TaskOut.model_validate(task)


def reorder_tasks(db: Session, user: User, data: TaskReorder) -> None:
    _lock_project(db, user, data.project_id)
    tasks = {t.id: t for t in repo.project_tasks(db, user.id, data.project_id)}
    if len(set(data.ordered_ids)) != len(data.ordered_ids) or set(data.ordered_ids) != set(tasks):
        raise ValidationFailed(
            "ordered_ids must list every task of the project exactly once.", field="ordered_ids", code="mismatch"
        )
    for position, task_id in enumerate(data.ordered_ids):
        tasks[task_id].position = position
    db.commit()


def delete_task(db: Session, user: User, task_id: uuid.UUID) -> None:
    db.delete(_get(db, user, task_id))
    db.commit()
