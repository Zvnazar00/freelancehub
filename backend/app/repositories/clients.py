import uuid

from sqlalchemy import func, or_, select, tuple_
from sqlalchemy.orm import Session

from app.models import Client, Project
from app.models.enums import ProjectStatus


def get_client(db: Session, user_id: uuid.UUID, client_id: uuid.UUID, *, for_update: bool = False) -> Client | None:
    stmt = select(Client).where(Client.id == client_id, Client.user_id == user_id)
    if for_update:
        stmt = stmt.with_for_update()
    return db.scalar(stmt)


def list_clients(
    db: Session,
    user_id: uuid.UUID,
    *,
    archived: bool,
    search: str | None,
    after: tuple[str, uuid.UUID] | None,
    limit: int,
) -> list[Client]:
    sort_name = func.lower(Client.name)
    stmt = select(Client).where(Client.user_id == user_id)
    stmt = stmt.where(Client.archived_at.is_not(None) if archived else Client.archived_at.is_(None))
    if search:
        pattern = f"%{_escape_like(search.lower())}%"
        stmt = stmt.where(
            or_(sort_name.like(pattern, escape="\\"), func.lower(Client.company).like(pattern, escape="\\"))
        )
    if after:
        stmt = stmt.where(tuple_(sort_name, Client.id) > tuple_(after[0], after[1]))
    return list(db.scalars(stmt.order_by(sort_name, Client.id).limit(limit)))


def active_project_counts(db: Session, user_id: uuid.UUID, client_ids: list[uuid.UUID]) -> dict[uuid.UUID, int]:
    if not client_ids:
        return {}
    rows = db.execute(
        select(Project.client_id, func.count())
        .where(
            Project.user_id == user_id,
            Project.client_id.in_(client_ids),
            Project.status == ProjectStatus.active,
            Project.archived_at.is_(None),
        )
        .group_by(Project.client_id)
    )
    return {client_id: count for client_id, count in rows}


def has_projects(db: Session, user_id: uuid.UUID, client_id: uuid.UUID) -> bool:
    return (
        db.scalar(
            select(func.count()).select_from(Project).where(Project.user_id == user_id, Project.client_id == client_id)
        )
        != 0
    )


def active_name_taken(db: Session, user_id: uuid.UUID, name: str, *, exclude_id: uuid.UUID | None = None) -> bool:
    stmt = select(Client.id).where(
        Client.user_id == user_id, func.lower(Client.name) == name.lower(), Client.archived_at.is_(None)
    )
    if exclude_id:
        stmt = stmt.where(Client.id != exclude_id)
    return db.scalar(stmt.limit(1)) is not None


def _escape_like(value: str) -> str:
    return value.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
