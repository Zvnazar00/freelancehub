from typing import Annotated

from fastapi import APIRouter, Depends, Request, Response, status

from app.api.deps import AppSettings, Auth, DbSession, client_ip, get_rate_limiter
from app.core.rate_limit import RateLimiter
from app.schemas.auth import LoginRequest, LogoutRequest, RefreshRequest, RegisterRequest, TokenPair, UserOut
from app.services import auth as service
from app.services.auth import IssuedTokens

router = APIRouter(prefix="/auth", tags=["auth"])
Limiter = Annotated[RateLimiter, Depends(get_rate_limiter)]


def _pair(tokens: IssuedTokens) -> TokenPair:
    return TokenPair(
        access_token=tokens.access_token,
        refresh_token=tokens.refresh_token,
        expires_in=tokens.expires_in,
        user=UserOut.model_validate(tokens.user),
    )


@router.post("/register", status_code=status.HTTP_201_CREATED)
def register(
    body: RegisterRequest, request: Request, db: DbSession, settings: AppSettings, limiter: Limiter
) -> TokenPair:
    if settings.rate_limit_enabled:
        limiter.hit(
            f"register:{client_ip(request)}", settings.register_rate_limit, settings.register_rate_window_seconds
        )
    return _pair(service.register(db, body, settings, request.headers.get("user-agent")))


@router.post("/login")
def login(body: LoginRequest, request: Request, db: DbSession, settings: AppSettings, limiter: Limiter) -> TokenPair:
    if settings.rate_limit_enabled:
        key = f"login:{client_ip(request)}:{str(body.email).lower()}"
        limiter.hit(key, settings.login_rate_limit, settings.login_rate_window_seconds)
    return _pair(service.login(db, body, settings, request.headers.get("user-agent")))


@router.post("/refresh")
def refresh(body: RefreshRequest, request: Request, db: DbSession, settings: AppSettings) -> TokenPair:
    return _pair(service.refresh(db, body.refresh_token, settings, request.headers.get("user-agent")))


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
def logout(body: LogoutRequest, db: DbSession) -> Response:
    service.logout(db, body.refresh_token)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post("/logout-all", status_code=status.HTTP_204_NO_CONTENT)
def logout_all(auth: Auth, db: DbSession) -> Response:
    service.logout_all(db, auth.user)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
