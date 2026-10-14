import uuid
from datetime import date

from sqlalchemy import func, select, tuple_
from sqlalchemy.orm import Session

from app.models import Task
from app.models.enums import TaskStatus

FAR_FUTURE = date(9999, 12, 31)


def get_task(db: Session, user_id: uuid.UUID, task_id: uuid.UUID) -> Task | None:
    return db.scalar(select(Task).where(Task.id == task_id, Task.user_id == user_id))


def list_tasks(
    db: Session,
    user_id: uuid.UUID,
    *,
    project_id: uuid.UUID | None,
    status: TaskStatus | None,
    due_before: date | None,
    after: tuple[str, uuid.UUID] | None,
    limit: int,
) -> list[Task]:
    stmt = select(Task).where(Task.user_id == user_id)
    if status:
        stmt = stmt.where(Task.status == status)
    if due_before:
        stmt = stmt.where(Task.due_date < due_before)
    if project_id:
        # Within a project: manual order.
        stmt = stmt.where(Task.project_id == project_id)
        if after:
            stmt = stmt.where(tuple_(Task.position, Task.id) > tuple_(int(after[0]), after[1]))
        stmt = stmt.order_by(Task.position, Task.id)
    else:
        # Across projects: soonest due first, undated last.
        due = func.coalesce(Task.due_date, FAR_FUTURE)
        if after:
            stmt = stmt.where(tuple_(due, Task.id) > tuple_(date.fromisoformat(after[0]), after[1]))
        stmt = stmt.order_by(due, Task.id)
    return list(db.scalars(stmt.limit(limit)))


def next_position(db: Session, project_id: uuid.UUID) -> int:
    current = db.scalar(select(func.max(Task.position)).where(Task.project_id == project_id))
    return 0 if current is None else current + 1


def project_tasks(db: Session, user_id: uuid.UUID, project_id: uuid.UUID) -> list[Task]:
    return list(db.scalars(select(Task).where(Task.user_id == user_id, Task.project_id == project_id)))
