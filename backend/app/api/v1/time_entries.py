import uuid
from datetime import date
from typing import Annotated

from fastapi import APIRouter, Depends, Header, Query, Response, status

from app.api.deps import Auth, DbSession
from app.api.idempotency import run_idempotent
from app.core.clock import Clock, get_clock
from app.core.pagination import DEFAULT_LIMIT, MAX_LIMIT
from app.schemas.time_entries import EntryPage, EntryUpdate, ManualEntryCreate, TimeEntryOut
from app.services import time_entries as service

router = APIRouter(prefix="/time-entries", tags=["time entries"])
Now = Annotated[Clock, Depends(get_clock)]


@router.get("")
def history(
    auth: Auth,
    db: DbSession,
    clock: Now,
    day_from: Annotated[date | None, Query(alias="from", description="Local date (user time zone), inclusive")] = None,
    day_to: Annotated[date | None, Query(alias="to", description="Local date (user time zone), inclusive")] = None,
    project_id: uuid.UUID | None = None,
    client_id: uuid.UUID | None = None,
    task_id: uuid.UUID | None = None,
    billable: bool | None = None,
    cursor: Annotated[str | None, Query(max_length=500)] = None,
    limit: Annotated[int, Query(ge=1, le=MAX_LIMIT)] = DEFAULT_LIMIT,
) -> EntryPage:
    return service.history(
        db,
        auth.user,
        day_from=day_from,
        day_to=day_to,
        project_id=project_id,
        client_id=client_id,
        task_id=task_id,
        billable=billable,
        cursor=cursor,
        limit=limit,
        now=clock(),
    )


@router.post("", status_code=status.HTTP_201_CREATED, response_model=TimeEntryOut)
def create_manual(
    body: ManualEntryCreate,
    auth: Auth,
    db: DbSession,
    clock: Now,
    idempotency_key: Annotated[str | None, Header(alias="Idempotency-Key")] = None,
) -> Response:
    now = clock()

    def mutation() -> tuple[int, TimeEntryOut]:
        entry = service.create_manual(db, auth.user, body, clock)
        return 201, service.one(db, auth.user, entry, clock())

    return run_idempotent(
        db, auth.user, idempotency_key, "POST /time-entries", body.model_dump(mode="json"), now, mutation
    )


@router.get("/{entry_id}")
def get_entry(entry_id: uuid.UUID, auth: Auth, db: DbSession, clock: Now) -> TimeEntryOut:
    return service.serialize(db, auth.user, [service.get_entry(db, auth.user, entry_id)], clock())[0]


@router.patch("/{entry_id}")
def update_entry(entry_id: uuid.UUID, body: EntryUpdate, auth: Auth, db: DbSession, clock: Now) -> TimeEntryOut:
    entry = service.update_entry(db, auth.user, entry_id, body, clock)
    db.commit()
    return service.one(db, auth.user, entry, clock())


@router.delete("/{entry_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_entry(entry_id: uuid.UUID, auth: Auth, db: DbSession) -> Response:
    service.delete_entry(db, auth.user, entry_id)
    db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)
