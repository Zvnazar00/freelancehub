"""Domain errors rendered as RFC 9457 Problem Details with a stable machine-readable `code`."""

from typing import Any


class AppError(Exception):
    status_code: int = 400
    code: str = "BAD_REQUEST"
    title: str = "Bad request"

    def __init__(
        self,
        detail: str | None = None,
        *,
        code: str | None = None,
        title: str | None = None,
        context: dict[str, Any] | None = None,
        headers: dict[str, str] | None = None,
    ) -> None:
        super().__init__(detail or self.title)
        self.detail = detail
        if code:
            self.code = code
        if title:
            self.title = title
        self.context = context
        self.headers = headers


class Unauthorized(AppError):
    status_code = 401
    code = "UNAUTHENTICATED"
    title = "Authentication required"


class NotFound(AppError):
    status_code = 404
    code = "NOT_FOUND"
    title = "Resource not found"


class Conflict(AppError):
    status_code = 409
    code = "CONFLICT"
    title = "Conflict"


class ValidationFailed(AppError):
    status_code = 422
    code = "VALIDATION_ERROR"
    title = "Validation failed"

    def __init__(
        self, detail: str, *, field: str | None = None, code: str | None = None, problem_code: str = "VALIDATION_ERROR"
    ) -> None:
        errors = [{"field": field, "message": detail, "code": code or "invalid"}] if field else None
        super().__init__(detail, code=problem_code, context={"errors": errors} if errors else None)
        self.errors = errors


class RateLimited(AppError):
    status_code = 429
    code = "RATE_LIMITED"
    title = "Too many requests"
