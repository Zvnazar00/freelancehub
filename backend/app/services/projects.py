import uuid
from datetime import UTC, datetime
from decimal import Decimal

from sqlalchemy.orm import Session

from app.core.errors import Conflict, NotFound, ValidationFailed
from app.core.pagination import cursor_uuid, decode_cursor, encode_cursor
from app.models import Client, Project, User
from app.models.enums import BillingType, ProjectStatus
from app.repositories import clients as clients_repo
from app.repositories import projects as repo
from app.repositories import time_entries as entries_repo
from app.schemas.common import Page, currency_amounts
from app.schemas.projects import ClientRef, ProjectCreate, ProjectOut, ProjectStats, ProjectUpdate


def _get(db: Session, user: User, project_id: uuid.UUID, *, for_update: bool = False) -> Project:
    project = repo.get_project(db, user.id, project_id, for_update=for_update)
    if project is None:
        raise NotFound("Project not found.")
    return project


def _owned_client(db: Session, user: User, client_id: uuid.UUID) -> Client:
    client = clients_repo.get_client(db, user.id, client_id)
    if client is None:
        # Same answer for "missing" and "someone else's" — no ID enumeration.
        raise NotFound("Client not found.")
    if client.archived_at is not None:
        raise Conflict("Archived clients cannot receive projects. Unarchive the client first.", code="CLIENT_ARCHIVED")
    return client


def _validate_billing(billing: BillingType, hourly_rate: Decimal | None, fixed_fee: Decimal | None) -> None:
    """Billing rules (docs/database.md §3.4), checked before the DB constraints for friendly errors."""
    if billing is BillingType.hourly and fixed_fee is not None:
        raise ValidationFailed("fixed_fee is only allowed for fixed-price projects.", field="fixed_fee")
    if billing is BillingType.fixed and fixed_fee is None:
        raise ValidationFailed("fixed_fee is required for fixed-price projects.", field="fixed_fee", code="missing")
    if billing is not BillingType.hourly and hourly_rate is not None:
        raise ValidationFailed("hourly_rate is only allowed for hourly projects.", field="hourly_rate")
    if billing is BillingType.non_billable and fixed_fee is not None:
        raise ValidationFailed("Non-billable projects cannot have a fee.", field="fixed_fee")


def _ensure_name_free(db: Session, client_id: uuid.UUID, name: str, exclude_id: uuid.UUID | None = None) -> None:
    if repo.active_name_taken(db, client_id, name, exclude_id=exclude_id):
        raise Conflict("This client already has an active project with this name.", code="NAME_TAKEN")


def _to_out(projects: list[Project], db: Session, user: User) -> list[ProjectOut]:
    names = repo.client_names(db, user.id, {p.client_id for p in projects})
    counts = repo.task_counts(db, user.id, [p.id for p in projects])
    totals = entries_repo.stopped_totals(db, user.id, project_ids=[p.id for p in projects])
    result = []
    for p in projects:
        total, done = counts.get(p.id, (0, 0))
        seconds, amounts = totals.get(p.id, (0, {}))
        result.append(
            ProjectOut(
                id=p.id,
                client=ClientRef(id=p.client_id, name=names.get(p.client_id, "")),
                name=p.name,
                description=p.description,
                status=p.status,
                billing_type=p.billing_type,
                hourly_rate=p.hourly_rate,
                fixed_fee=p.fixed_fee,
                currency=p.currency,
                budget_hours=p.budget_hours,
                deadline=p.deadline,
                color=p.color,
                archived_at=p.archived_at,
                created_at=p.created_at,
                updated_at=p.updated_at,
                stats=ProjectStats(
                    tasks_total=total, tasks_done=done, tracked_seconds=seconds, unbilled=currency_amounts(amounts)
                ),
            )
        )
    return result


def list_projects(
    db: Session,
    user: User,
    *,
    client_id: uuid.UUID | None,
    status: ProjectStatus | None,
    archived: bool,
    search: str | None,
    cursor: str | None,
    limit: int,
) -> Page[ProjectOut]:
    after = None
    if cursor:
        name, raw_id = decode_cursor(cursor, 2)
        after = (name, cursor_uuid(raw_id))
    rows = repo.list_projects(
        db, user.id, client_id=client_id, status=status, archived=archived, search=search, after=after, limit=limit + 1
    )
    page, has_more = rows[:limit], len(rows) > limit
    next_cursor = encode_cursor([page[-1].name.lower(), page[-1].id]) if has_more and page else None
    return Page[ProjectOut](items=_to_out(page, db, user), next_cursor=next_cursor)


def get_project(db: Session, user: User, project_id: uuid.UUID) -> ProjectOut:
    return _to_out([_get(db, user, project_id)], db, user)[0]


def create_project(db: Session, user: User, data: ProjectCreate) -> ProjectOut:
    client = _owned_client(db, user, data.client_id)
    _validate_billing(data.billing_type, data.hourly_rate, data.fixed_fee)
    _ensure_name_free(db, client.id, data.name)
    project = Project(
        user_id=user.id,
        client_id=client.id,
        name=data.name,
        description=data.description or None,
        status=data.status,
        billing_type=data.billing_type,
        hourly_rate=data.hourly_rate,
        fixed_fee=data.fixed_fee,
        currency=data.currency or client.currency,
        budget_hours=data.budget_hours,
        deadline=data.deadline,
        color=data.color,
    )
    db.add(project)
    db.commit()
    db.refresh(project)
    return get_project(db, user, project.id)


def update_project(db: Session, user: User, project_id: uuid.UUID, data: ProjectUpdate) -> ProjectOut:
    project = _get(db, user, project_id, for_update=True)
    changes = data.model_dump(exclude_unset=True)
    if "client_id" in changes and changes["client_id"] != project.client_id:
        _owned_client(db, user, changes["client_id"])
    billing = changes.get("billing_type", project.billing_type)
    _validate_billing(
        billing,
        changes.get("hourly_rate", project.hourly_rate if billing is BillingType.hourly else None),
        changes.get("fixed_fee", project.fixed_fee if billing is BillingType.fixed else None),
    )
    # Switching billing type clears values that no longer apply.
    if billing is not BillingType.hourly:
        changes["hourly_rate"] = None
    if billing is not BillingType.fixed:
        changes["fixed_fee"] = None
    if project.archived_at is None and ({"name", "client_id"} & changes.keys()):
        _ensure_name_free(
            db, changes.get("client_id", project.client_id), changes.get("name", project.name), project.id
        )
    for field, value in changes.items():
        setattr(project, field, value)
    db.commit()
    return get_project(db, user, project.id)


def set_archived(db: Session, user: User, project_id: uuid.UUID, archived: bool) -> ProjectOut:
    project = _get(db, user, project_id, for_update=True)
    if archived and project.archived_at is None:
        project.archived_at = datetime.now(UTC)
    elif not archived and project.archived_at is not None:
        _ensure_name_free(db, project.client_id, project.name, project.id)
        project.archived_at = None
    db.commit()
    return get_project(db, user, project.id)


def delete_project(db: Session, user: User, project_id: uuid.UUID) -> None:
    project = _get(db, user, project_id, for_update=True)
    if entries_repo.project_has_entries(db, user.id, project.id):
        raise Conflict("This project has tracked time. Archive it instead.", code="RESOURCE_IN_USE")
    db.delete(project)  # tasks are removed by ON DELETE CASCADE
    db.commit()
