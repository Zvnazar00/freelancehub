from fastapi import APIRouter, Response, status

from app.api.deps import Auth, DbSession
from app.schemas.auth import ChangePasswordRequest, UserOut, UserUpdate
from app.services import auth as auth_service
from app.services import users as service

router = APIRouter(prefix="/me", tags=["profile"])


@router.get("")
def get_me(auth: Auth) -> UserOut:
    return UserOut.model_validate(auth.user)


@router.patch("")
def update_me(body: UserUpdate, auth: Auth, db: DbSession) -> UserOut:
    return UserOut.model_validate(service.update_profile(db, auth.user, body))


@router.post("/password", status_code=status.HTTP_204_NO_CONTENT)
def change_password(body: ChangePasswordRequest, auth: Auth, db: DbSession) -> Response:
    auth_service.change_password(db, auth.user, auth.session_id, body)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
