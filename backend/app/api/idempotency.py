"""Idempotency-Key handling (docs/time-tracking.md §Retries).

The key row and the stored response are written in the SAME transaction as the mutation:
  * first request:   INSERT key → run mutation → UPDATE key with response → COMMIT (all or nothing);
  * concurrent copy: its INSERT blocks on the primary key until the first commits, then replays;
  * failed request:  the transaction rolls back, key included — errors are never cached, a retry re-runs;
  * same key, different payload → 422 IDEMPOTENCY_KEY_REUSED.
"""

import hashlib
import json
import re
from collections.abc import Callable
from datetime import datetime, timedelta
from typing import Any

from fastapi.responses import Response
from pydantic import BaseModel
from sqlalchemy import delete, select, update
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from app.core.errors import AppError, ValidationFailed
from app.models import IdempotencyKey, User

KEY_PATTERN = re.compile(r"^[A-Za-z0-9_\-:.]{8,100}$")
RETENTION = timedelta(hours=48)


class IdempotencyKeyRequired(AppError):
    status_code = 428
    code = "IDEMPOTENCY_KEY_REQUIRED"
    title = "Idempotency key required"


def request_fingerprint(endpoint: str, payload: dict[str, Any]) -> str:
    canonical = json.dumps(
        {"endpoint": endpoint, "payload": payload}, sort_keys=True, separators=(",", ":"), default=str
    )
    return hashlib.sha256(canonical.encode()).hexdigest()


def run_idempotent(
    db: Session,
    user: User,
    key: str | None,
    endpoint: str,
    payload: dict[str, Any],
    now: datetime,
    mutation: Callable[[], tuple[int, BaseModel | None]],
) -> Response:
    if not key:
        raise IdempotencyKeyRequired("Send an Idempotency-Key header (e.g. a UUID) with this request.")
    if not KEY_PATTERN.fullmatch(key):
        raise ValidationFailed(
            "Idempotency-Key must be 8-100 characters [A-Za-z0-9_-:.].", field="Idempotency-Key", code="invalid_key"
        )
    fingerprint = request_fingerprint(endpoint, payload)

    # Opportunistic cleanup of this user's expired keys keeps the table small without a cron job.
    db.execute(
        delete(IdempotencyKey).where(IdempotencyKey.user_id == user.id, IdempotencyKey.created_at < now - RETENTION)
    )
    claimed = db.scalar(
        insert(IdempotencyKey)
        .values(
            user_id=user.id,
            key=key,
            endpoint=endpoint,
            request_hash=fingerprint,
            status_code=0,
            response_body="",
            created_at=now,
        )
        .on_conflict_do_nothing(index_elements=["user_id", "key"])
        .returning(IdempotencyKey.key)
    )
    if claimed is None:
        stored = db.execute(
            select(IdempotencyKey.request_hash, IdempotencyKey.status_code, IdempotencyKey.response_body).where(
                IdempotencyKey.user_id == user.id, IdempotencyKey.key == key
            )
        ).one()
        db.rollback()
        if stored.request_hash != fingerprint:
            raise ValidationFailed(
                "This Idempotency-Key was already used for a different request.",
                field="Idempotency-Key",
                code="reused",
                problem_code="IDEMPOTENCY_KEY_REUSED",
            )
        return _response(stored.status_code, stored.response_body, replayed=True)

    try:
        status_code, model = mutation()
    except Exception:
        db.rollback()
        raise
    body = model.model_dump_json() if model is not None else "null"
    db.execute(
        update(IdempotencyKey)
        .where(IdempotencyKey.user_id == user.id, IdempotencyKey.key == key)
        .values(status_code=status_code, response_body=body)
    )
    db.commit()
    return _response(status_code, body, replayed=False)


def _response(status_code: int, body: str, *, replayed: bool) -> Response:
    headers = {"Idempotent-Replayed": "true"} if replayed else {}
    return Response(content=body, status_code=status_code, headers=headers, media_type="application/json")


def run_optionally_idempotent(
    db: Session,
    user: User,
    key: str | None,
    endpoint: str,
    payload: dict[str, Any],
    now: datetime,
    mutation: Callable[[], tuple[int, BaseModel | None]],
) -> Response:
    """For POSTs where the key is recommended but optional (invoices, payments): with a key, retries replay."""
    if key:
        return run_idempotent(db, user, key, endpoint, payload, now, mutation)
    status_code, model = mutation()
    db.commit()
    return _response(status_code, model.model_dump_json() if model is not None else "null", replayed=False)
