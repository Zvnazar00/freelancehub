import uuid
from datetime import date
from typing import Annotated

from fastapi import APIRouter, Query, Response, status

from app.api.deps import Auth, DbSession
from app.core.pagination import DEFAULT_LIMIT, MAX_LIMIT
from app.models.enums import TaskStatus
from app.schemas.common import Page
from app.schemas.tasks import TaskCreate, TaskOut, TaskReorder, TaskUpdate
from app.services import tasks as service

router = APIRouter(prefix="/tasks", tags=["tasks"])


@router.get("")
def list_tasks(
    auth: Auth,
    db: DbSession,
    project_id: uuid.UUID | None = None,
    status_filter: Annotated[TaskStatus | None, Query(alias="status")] = None,
    due_before: date | None = None,
    cursor: Annotated[str | None, Query(max_length=500)] = None,
    limit: Annotated[int, Query(ge=1, le=MAX_LIMIT)] = DEFAULT_LIMIT,
) -> Page[TaskOut]:
    return service.list_tasks(
        db, auth.user, project_id=project_id, status=status_filter, due_before=due_before, cursor=cursor, limit=limit
    )


@router.post("", status_code=status.HTTP_201_CREATED)
def create_task(body: TaskCreate, auth: Auth, db: DbSession) -> TaskOut:
    return service.create_task(db, auth.user, body)


# Declared before /{task_id} so "reorder" is never parsed as an ID.
@router.post("/reorder", status_code=status.HTTP_204_NO_CONTENT)
def reorder_tasks(body: TaskReorder, auth: Auth, db: DbSession) -> Response:
    service.reorder_tasks(db, auth.user, body)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get("/{task_id}")
def get_task(task_id: uuid.UUID, auth: Auth, db: DbSession) -> TaskOut:
    return service.get_task(db, auth.user, task_id)


@router.patch("/{task_id}")
def update_task(task_id: uuid.UUID, body: TaskUpdate, auth: Auth, db: DbSession) -> TaskOut:
    return service.update_task(db, auth.user, task_id, body)


@router.delete("/{task_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_task(task_id: uuid.UUID, auth: Auth, db: DbSession) -> Response:
    service.delete_task(db, auth.user, task_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
