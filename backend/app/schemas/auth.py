import uuid
from typing import Annotated

from pydantic import EmailStr, Field, StringConstraints, model_validator

from app.schemas.common import Currency, Rate, ResponseModel, StrictModel, Timestamped, TimeZoneName

Password = Annotated[str, StringConstraints(min_length=10, max_length=128)]
FullName = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=120)]


class RegisterRequest(StrictModel):
    email: EmailStr
    password: Password
    full_name: FullName
    timezone: TimeZoneName = "UTC"
    default_currency: Currency = "USD"

    @model_validator(mode="after")
    def _password_not_email(self) -> "RegisterRequest":
        if self.password.strip().lower() == str(self.email).lower():
            raise ValueError("password must not be the same as the email")
        return self


class LoginRequest(StrictModel):
    email: EmailStr
    password: Annotated[str, StringConstraints(min_length=1, max_length=128)]


class RefreshRequest(StrictModel):
    refresh_token: Annotated[str, StringConstraints(min_length=20, max_length=200)]


class LogoutRequest(RefreshRequest):
    pass


class ChangePasswordRequest(StrictModel):
    current_password: Annotated[str, StringConstraints(min_length=1, max_length=128)]
    new_password: Password


class UserOut(Timestamped):
    id: uuid.UUID
    email: str
    full_name: str
    timezone: str
    default_currency: str
    default_hourly_rate: Rate | None
    week_start: int


class UserUpdate(StrictModel):
    full_name: FullName | None = None
    timezone: TimeZoneName | None = None
    default_currency: Currency | None = None
    default_hourly_rate: Rate | None = None
    week_start: Annotated[int, Field(ge=1, le=7)] | None = None

    @model_validator(mode="after")
    def _week_start_values(self) -> "UserUpdate":
        if self.week_start is not None and self.week_start not in (1, 7):
            raise ValueError("week_start must be 1 (Monday) or 7 (Sunday)")
        for field in ("full_name", "timezone", "default_currency", "week_start"):
            if field in self.model_fields_set and getattr(self, field) is None:
                raise ValueError(f"{field} cannot be null")
        return self


class TokenPair(ResponseModel):
    access_token: str
    token_type: str = "bearer"  # noqa: S105 - OAuth2 token type, not a secret
    expires_in: int
    refresh_token: str
    user: UserOut
