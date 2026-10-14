import uuid
from typing import Annotated

from fastapi import APIRouter, Query, Response, status

from app.api.deps import Auth, DbSession
from app.core.pagination import DEFAULT_LIMIT, MAX_LIMIT
from app.schemas.clients import ClientCreate, ClientOut, ClientUpdate
from app.schemas.common import Page
from app.services import clients as service

router = APIRouter(prefix="/clients", tags=["clients"])


@router.get("")
def list_clients(
    auth: Auth,
    db: DbSession,
    search: Annotated[str | None, Query(max_length=100)] = None,
    archived: bool = False,
    cursor: Annotated[str | None, Query(max_length=500)] = None,
    limit: Annotated[int, Query(ge=1, le=MAX_LIMIT)] = DEFAULT_LIMIT,
) -> Page[ClientOut]:
    return service.list_clients(db, auth.user, archived=archived, search=search, cursor=cursor, limit=limit)


@router.post("", status_code=status.HTTP_201_CREATED)
def create_client(body: ClientCreate, auth: Auth, db: DbSession) -> ClientOut:
    return service.create_client(db, auth.user, body)


@router.get("/{client_id}")
def get_client(client_id: uuid.UUID, auth: Auth, db: DbSession) -> ClientOut:
    return service.get_client(db, auth.user, client_id)


@router.patch("/{client_id}")
def update_client(client_id: uuid.UUID, body: ClientUpdate, auth: Auth, db: DbSession) -> ClientOut:
    return service.update_client(db, auth.user, client_id, body)


@router.post("/{client_id}/archive")
def archive_client(client_id: uuid.UUID, auth: Auth, db: DbSession) -> ClientOut:
    return service.set_archived(db, auth.user, client_id, archived=True)


@router.post("/{client_id}/unarchive")
def unarchive_client(client_id: uuid.UUID, auth: Auth, db: DbSession) -> ClientOut:
    return service.set_archived(db, auth.user, client_id, archived=False)


@router.delete("/{client_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_client(client_id: uuid.UUID, auth: Auth, db: DbSession) -> Response:
    service.delete_client(db, auth.user, client_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
