import uuid

from sqlalchemy import case, func, or_, select, tuple_
from sqlalchemy.orm import Session

from app.models import Client, Project, Task
from app.models.enums import ProjectStatus, TaskStatus
from app.repositories.clients import _escape_like


def get_project(db: Session, user_id: uuid.UUID, project_id: uuid.UUID, *, for_update: bool = False) -> Project | None:
    stmt = select(Project).where(Project.id == project_id, Project.user_id == user_id)
    if for_update:
        stmt = stmt.with_for_update()
    return db.scalar(stmt)


def list_projects(
    db: Session,
    user_id: uuid.UUID,
    *,
    client_id: uuid.UUID | None,
    status: ProjectStatus | None,
    archived: bool,
    search: str | None,
    after: tuple[str, uuid.UUID] | None,
    limit: int,
) -> list[Project]:
    sort_name = func.lower(Project.name)
    stmt = select(Project).where(Project.user_id == user_id)
    stmt = stmt.where(Project.archived_at.is_not(None) if archived else Project.archived_at.is_(None))
    if client_id:
        stmt = stmt.where(Project.client_id == client_id)
    if status:
        stmt = stmt.where(Project.status == status)
    if search:
        pattern = f"%{_escape_like(search.lower())}%"
        stmt = stmt.join(Client, Client.id == Project.client_id).where(
            or_(sort_name.like(pattern, escape="\\"), func.lower(Client.name).like(pattern, escape="\\"))
        )
    if after:
        stmt = stmt.where(tuple_(sort_name, Project.id) > tuple_(after[0], after[1]))
    return list(db.scalars(stmt.order_by(sort_name, Project.id).limit(limit)))


def client_names(db: Session, user_id: uuid.UUID, client_ids: set[uuid.UUID]) -> dict[uuid.UUID, str]:
    if not client_ids:
        return {}
    rows = db.execute(select(Client.id, Client.name).where(Client.user_id == user_id, Client.id.in_(client_ids)))
    return {cid: name for cid, name in rows}


def task_counts(db: Session, user_id: uuid.UUID, project_ids: list[uuid.UUID]) -> dict[uuid.UUID, tuple[int, int]]:
    if not project_ids:
        return {}
    done = func.sum(case((Task.status == TaskStatus.done, 1), else_=0))
    rows = db.execute(
        select(Task.project_id, func.count(), done)
        .where(Task.user_id == user_id, Task.project_id.in_(project_ids))
        .group_by(Task.project_id)
    )
    return {pid: (int(total), int(done_count or 0)) for pid, total, done_count in rows}


def active_name_taken(db: Session, client_id: uuid.UUID, name: str, *, exclude_id: uuid.UUID | None = None) -> bool:
    stmt = select(Project.id).where(
        Project.client_id == client_id, func.lower(Project.name) == name.lower(), Project.archived_at.is_(None)
    )
    if exclude_id:
        stmt = stmt.where(Project.id != exclude_id)
    return db.scalar(stmt.limit(1)) is not None
