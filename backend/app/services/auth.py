"""Registration, login, refresh-token rotation with reuse detection, logout (docs/architecture.md §6)."""

import logging
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core import security
from app.core.config import Settings
from app.core.errors import Conflict, Unauthorized, ValidationFailed
from app.models import RefreshToken, User
from app.repositories import users as repo
from app.schemas.auth import ChangePasswordRequest, LoginRequest, RegisterRequest

log = logging.getLogger("app.auth")


@dataclass(frozen=True)
class IssuedTokens:
    user: User
    access_token: str
    refresh_token: str
    expires_in: int


def _now() -> datetime:
    return datetime.now(UTC)


def _issue(
    db: Session, user: User, family_id: uuid.UUID, settings: Settings, user_agent: str | None
) -> tuple[RefreshToken, IssuedTokens]:
    raw = security.generate_refresh_token()
    token = RefreshToken(
        user_id=user.id,
        family_id=family_id,
        token_hash=security.hash_refresh_token(raw),
        expires_at=_now() + timedelta(seconds=settings.refresh_token_ttl_seconds),
        user_agent=(user_agent or "")[:200] or None,
    )
    db.add(token)
    access = security.create_access_token(user.id, family_id, settings)
    return token, IssuedTokens(user, access, raw, settings.access_token_ttl_seconds)


def register(db: Session, data: RegisterRequest, settings: Settings, user_agent: str | None) -> IssuedTokens:
    email = str(data.email).strip().lower()
    if repo.get_user_by_email(db, email):
        raise Conflict("An account with this email already exists.", code="EMAIL_TAKEN")
    user = User(
        email=email,
        password_hash=security.hash_password(data.password),
        full_name=data.full_name,
        timezone=data.timezone,
        default_currency=data.default_currency,
    )
    db.add(user)
    try:
        db.flush()
    except IntegrityError as exc:  # concurrent registration with the same email
        db.rollback()
        raise Conflict("An account with this email already exists.", code="EMAIL_TAKEN") from exc
    _, tokens = _issue(db, user, uuid.uuid4(), settings, user_agent)
    db.commit()
    log.info("user registered", extra={"data": {"user_id": str(user.id)}})
    return tokens


def login(db: Session, data: LoginRequest, settings: Settings, user_agent: str | None) -> IssuedTokens:
    user = repo.get_user_by_email(db, str(data.email).strip().lower())
    # verify_password runs a full Argon2 check even for unknown emails (timing equalisation).
    if not security.verify_password(user.password_hash if user else None, data.password) or user is None:
        log.info("login failed")
        raise Unauthorized("Email or password is incorrect.", code="INVALID_CREDENTIALS")
    if security.needs_rehash(user.password_hash):
        user.password_hash = security.hash_password(data.password)
    _, tokens = _issue(db, user, uuid.uuid4(), settings, user_agent)
    db.commit()
    return tokens


def refresh(db: Session, raw_token: str, settings: Settings, user_agent: str | None) -> IssuedTokens:
    now = _now()
    current = repo.get_refresh_token_for_update(db, security.hash_refresh_token(raw_token))
    if current is None or current.expires_at <= now:
        raise Unauthorized("Refresh token is invalid or expired.", code="TOKEN_INVALID")

    if current.revoked_at is not None:
        rotated_recently = (
            current.rotated_at is not None
            and (now - current.rotated_at).total_seconds() <= settings.refresh_reuse_grace_seconds
        )
        if rotated_recently:
            # Likely a network retry of a refresh that already succeeded: reject without punishing the session.
            raise Unauthorized("Refresh token was already used.", code="TOKEN_ROTATED")
        # Reuse of an old token: assume theft and kill the whole session family.
        repo.revoke_family(db, current.family_id, now)
        db.commit()
        log.warning("refresh token reuse detected", extra={"data": {"family_id": str(current.family_id)}})
        raise Unauthorized("Refresh token is invalid or expired.", code="TOKEN_INVALID")

    user = db.get(User, current.user_id)
    if user is None:  # pragma: no cover - FK cascade deletes tokens with the user
        raise Unauthorized(code="TOKEN_INVALID")
    new_token, tokens = _issue(db, user, current.family_id, settings, user_agent)
    db.flush()
    current.revoked_at = now
    current.rotated_at = now
    current.replaced_by_id = new_token.id
    db.commit()
    return tokens


def logout(db: Session, raw_token: str) -> None:
    """Revokes the session family of the given refresh token. Silent for unknown tokens (no oracle)."""
    token = repo.get_refresh_token_for_update(db, security.hash_refresh_token(raw_token))
    if token is not None:
        repo.revoke_family(db, token.family_id, _now())
        db.commit()


def logout_all(db: Session, user: User) -> None:
    repo.revoke_user_tokens(db, user.id, _now())
    db.commit()


def change_password(db: Session, user: User, session_id: uuid.UUID, data: ChangePasswordRequest) -> None:
    if not security.verify_password(user.password_hash, data.current_password):
        raise ValidationFailed("Current password is incorrect.", field="current_password", code="invalid_password")
    if data.new_password == data.current_password:
        raise ValidationFailed("New password must differ from the current one.", field="new_password", code="unchanged")
    user.password_hash = security.hash_password(data.new_password)
    repo.revoke_user_tokens(db, user.id, _now(), except_family=session_id)
    db.commit()
