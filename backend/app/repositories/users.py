import uuid
from datetime import datetime

from sqlalchemy import select, update
from sqlalchemy.orm import Session

from app.models import RefreshToken, User


def get_user(db: Session, user_id: uuid.UUID) -> User | None:
    return db.get(User, user_id)


def get_user_by_email(db: Session, email: str) -> User | None:
    # users.email is CITEXT, so the comparison is case-insensitive in the database.
    return db.scalar(select(User).where(User.email == email))


def get_refresh_token_for_update(db: Session, token_hash: str) -> RefreshToken | None:
    """Row lock serialises concurrent refreshes of the same token."""
    return db.scalar(select(RefreshToken).where(RefreshToken.token_hash == token_hash).with_for_update())


def revoke_family(db: Session, family_id: uuid.UUID, now: datetime) -> None:
    db.execute(
        update(RefreshToken)
        .where(RefreshToken.family_id == family_id, RefreshToken.revoked_at.is_(None))
        .values(revoked_at=now)
    )


def revoke_user_tokens(
    db: Session, user_id: uuid.UUID, now: datetime, *, except_family: uuid.UUID | None = None
) -> None:
    stmt = update(RefreshToken).where(RefreshToken.user_id == user_id, RefreshToken.revoked_at.is_(None))
    if except_family is not None:
        stmt = stmt.where(RefreshToken.family_id != except_family)
    db.execute(stmt.values(revoked_at=now))
