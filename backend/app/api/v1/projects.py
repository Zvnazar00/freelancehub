import uuid
from typing import Annotated

from fastapi import APIRouter, Query, Response, status

from app.api.deps import Auth, DbSession
from app.core.pagination import DEFAULT_LIMIT, MAX_LIMIT
from app.models.enums import ProjectStatus
from app.schemas.common import Page
from app.schemas.projects import ProjectCreate, ProjectOut, ProjectUpdate
from app.services import projects as service

router = APIRouter(prefix="/projects", tags=["projects"])


@router.get("")
def list_projects(
    auth: Auth,
    db: DbSession,
    client_id: uuid.UUID | None = None,
    status_filter: Annotated[ProjectStatus | None, Query(alias="status")] = None,
    archived: bool = False,
    search: Annotated[str | None, Query(max_length=100)] = None,
    cursor: Annotated[str | None, Query(max_length=500)] = None,
    limit: Annotated[int, Query(ge=1, le=MAX_LIMIT)] = DEFAULT_LIMIT,
) -> Page[ProjectOut]:
    return service.list_projects(
        db,
        auth.user,
        client_id=client_id,
        status=status_filter,
        archived=archived,
        search=search,
        cursor=cursor,
        limit=limit,
    )


@router.post("", status_code=status.HTTP_201_CREATED)
def create_project(body: ProjectCreate, auth: Auth, db: DbSession) -> ProjectOut:
    return service.create_project(db, auth.user, body)


@router.get("/{project_id}")
def get_project(project_id: uuid.UUID, auth: Auth, db: DbSession) -> ProjectOut:
    return service.get_project(db, auth.user, project_id)


@router.patch("/{project_id}")
def update_project(project_id: uuid.UUID, body: ProjectUpdate, auth: Auth, db: DbSession) -> ProjectOut:
    return service.update_project(db, auth.user, project_id, body)


@router.post("/{project_id}/archive")
def archive_project(project_id: uuid.UUID, auth: Auth, db: DbSession) -> ProjectOut:
    return service.set_archived(db, auth.user, project_id, archived=True)


@router.post("/{project_id}/unarchive")
def unarchive_project(project_id: uuid.UUID, auth: Auth, db: DbSession) -> ProjectOut:
    return service.set_archived(db, auth.user, project_id, archived=False)


@router.delete("/{project_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_project(project_id: uuid.UUID, auth: Auth, db: DbSession) -> Response:
    service.delete_project(db, auth.user, project_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
