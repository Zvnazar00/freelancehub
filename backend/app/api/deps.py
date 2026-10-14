import uuid
from dataclasses import dataclass
from typing import Annotated

from fastapi import Depends, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.orm import Session

from app.core.config import Settings, get_settings
from app.core.errors import Unauthorized
from app.core.rate_limit import RateLimiter
from app.core.security import TokenError, decode_access_token
from app.db.session import get_db
from app.models import User

_bearer = HTTPBearer(auto_error=False, description="Access token from /auth/login or /auth/refresh")

DbSession = Annotated[Session, Depends(get_db)]
AppSettings = Annotated[Settings, Depends(get_settings)]


@dataclass(frozen=True)
class CurrentUser:
    user: User
    session_id: uuid.UUID


def get_current_user(
    db: DbSession,
    settings: AppSettings,
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(_bearer)],
) -> CurrentUser:
    if credentials is None or credentials.scheme.lower() != "bearer":
        raise Unauthorized("Missing bearer token.", headers={"WWW-Authenticate": "Bearer"})
    try:
        claims = decode_access_token(credentials.credentials, settings)
    except TokenError as exc:
        raise Unauthorized(
            "Access token is invalid or expired.", code=exc.code, headers={"WWW-Authenticate": "Bearer"}
        ) from exc
    # The user ID comes only from the signed token, never from the request body or query.
    user = db.get(User, claims.user_id)
    if user is None:
        raise Unauthorized("Access token is invalid or expired.", code="TOKEN_INVALID")
    return CurrentUser(user=user, session_id=claims.session_id)


Auth = Annotated[CurrentUser, Depends(get_current_user)]


def get_rate_limiter(request: Request) -> RateLimiter:
    limiter: RateLimiter = request.app.state.rate_limiter
    return limiter


def client_ip(request: Request) -> str:
    # Behind a reverse proxy, configure uvicorn --proxy-headers so this reflects the real client.
    return request.client.host if request.client else "unknown"
