import uuid
from datetime import UTC, datetime
from decimal import Decimal

from sqlalchemy.orm import Session

from app.core.errors import Conflict, NotFound
from app.core.pagination import cursor_uuid, decode_cursor, encode_cursor
from app.models import Client, User
from app.repositories import clients as repo
from app.repositories import time_entries as entries_repo
from app.schemas.clients import ClientCreate, ClientOut, ClientStats, ClientUpdate
from app.schemas.common import Page, currency_amounts


def _get(db: Session, user: User, client_id: uuid.UUID, *, for_update: bool = False) -> Client:
    client = repo.get_client(db, user.id, client_id, for_update=for_update)
    if client is None:
        raise NotFound("Client not found.")
    return client


def _many(db: Session, user: User, clients: list[Client]) -> list[ClientOut]:
    ids = [c.id for c in clients]
    counts = repo.active_project_counts(db, user.id, ids)
    totals = entries_repo.stopped_totals(db, user.id, client_ids=ids)
    return [_out(c, counts.get(c.id, 0), *totals.get(c.id, (0, {}))) for c in clients]


def _out(
    client: Client, active_projects: int, tracked_seconds: int = 0, unbilled: dict[str, Decimal] | None = None
) -> ClientOut:
    return ClientOut(
        id=client.id,
        name=client.name,
        email=client.email,
        company=client.company,
        notes=client.notes,
        default_hourly_rate=client.default_hourly_rate,
        currency=client.currency,
        archived_at=client.archived_at,
        created_at=client.created_at,
        updated_at=client.updated_at,
        stats=ClientStats(
            active_projects=active_projects,
            tracked_seconds=tracked_seconds,
            unbilled=currency_amounts(unbilled or {}),
        ),
    )


def _ensure_name_free(db: Session, user: User, name: str, exclude_id: uuid.UUID | None = None) -> None:
    if repo.active_name_taken(db, user.id, name, exclude_id=exclude_id):
        raise Conflict("You already have an active client with this name.", code="NAME_TAKEN")


def list_clients(
    db: Session, user: User, *, archived: bool, search: str | None, cursor: str | None, limit: int
) -> Page[ClientOut]:
    after = None
    if cursor:
        name, raw_id = decode_cursor(cursor, 2)
        after = (name, cursor_uuid(raw_id))
    rows = repo.list_clients(db, user.id, archived=archived, search=search, after=after, limit=limit + 1)
    page, has_more = rows[:limit], len(rows) > limit
    next_cursor = encode_cursor([page[-1].name.lower(), page[-1].id]) if has_more and page else None
    return Page[ClientOut](items=_many(db, user, page), next_cursor=next_cursor)


def get_client(db: Session, user: User, client_id: uuid.UUID) -> ClientOut:
    client = _get(db, user, client_id)
    return _many(db, user, [client])[0]


def create_client(db: Session, user: User, data: ClientCreate) -> ClientOut:
    _ensure_name_free(db, user, data.name)
    client = Client(
        user_id=user.id,
        name=data.name,
        email=str(data.email).lower() if data.email else None,
        company=data.company or None,
        notes=data.notes or None,
        default_hourly_rate=data.default_hourly_rate,
        currency=data.currency or user.default_currency,
    )
    db.add(client)
    db.commit()
    db.refresh(client)
    return _out(client, 0)


def update_client(db: Session, user: User, client_id: uuid.UUID, data: ClientUpdate) -> ClientOut:
    client = _get(db, user, client_id, for_update=True)
    changes = data.model_dump(exclude_unset=True)
    if "name" in changes and client.archived_at is None:
        _ensure_name_free(db, user, changes["name"], exclude_id=client.id)
    if "email" in changes and changes["email"] is not None:
        changes["email"] = str(changes["email"]).lower()
    for field, value in changes.items():
        setattr(client, field, value)
    db.commit()
    db.refresh(client)
    return get_client(db, user, client.id)


def set_archived(db: Session, user: User, client_id: uuid.UUID, archived: bool) -> ClientOut:
    client = _get(db, user, client_id, for_update=True)
    if archived and client.archived_at is None:
        client.archived_at = datetime.now(UTC)
    elif not archived and client.archived_at is not None:
        _ensure_name_free(db, user, client.name, exclude_id=client.id)
        client.archived_at = None
    db.commit()
    return get_client(db, user, client.id)


def delete_client(db: Session, user: User, client_id: uuid.UUID) -> None:
    client = _get(db, user, client_id, for_update=True)
    if repo.has_projects(db, user.id, client.id):
        raise Conflict("This client has projects. Archive it instead.", code="RESOURCE_IN_USE")
    db.delete(client)
    db.commit()
