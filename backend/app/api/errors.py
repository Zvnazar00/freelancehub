"""Maps every error to RFC 9457 Problem Details (application/problem+json) with a stable `code`."""

import logging
from typing import Any

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.core.errors import AppError
from app.core.logging import request_id_var

log = logging.getLogger("app.errors")

_HTTP_CODES = {
    400: ("BAD_REQUEST", "Bad request"),
    401: ("UNAUTHENTICATED", "Authentication required"),
    403: ("FORBIDDEN", "Forbidden"),
    404: ("NOT_FOUND", "Resource not found"),
    405: ("METHOD_NOT_ALLOWED", "Method not allowed"),
    429: ("RATE_LIMITED", "Too many requests"),
}


def _slug(code: str) -> str:
    return code.lower().replace("_", "-")


def problem(
    status: int,
    code: str,
    title: str,
    detail: str | None = None,
    *,
    errors: list[dict[str, Any]] | None = None,
    context: dict[str, Any] | None = None,
    headers: dict[str, str] | None = None,
) -> JSONResponse:
    body: dict[str, Any] = {
        "type": f"https://freelancehub.dev/errors/{_slug(code)}",
        "title": title,
        "status": status,
        "code": code,
        "detail": detail,
        "errors": errors,
        "context": context,
        "request_id": request_id_var.get(),
    }
    return JSONResponse(body, status_code=status, headers=headers, media_type="application/problem+json")


def _field(loc: tuple[Any, ...]) -> str | None:
    parts = [str(p) for p in loc if p not in ("body", "query", "path", "header")]
    return ".".join(parts) or None


def install(app: FastAPI) -> None:
    @app.exception_handler(AppError)
    async def _app_error(_: Request, exc: AppError) -> JSONResponse:
        context = exc.context
        errors = None
        if context and "errors" in context:
            errors = context["errors"]
            context = {k: v for k, v in context.items() if k != "errors"} or None
        return problem(
            exc.status_code, exc.code, exc.title, exc.detail, errors=errors, context=context, headers=exc.headers
        )

    @app.exception_handler(RequestValidationError)
    async def _validation(_: Request, exc: RequestValidationError) -> JSONResponse:
        errors = [
            {
                "field": _field(tuple(e.get("loc", ()))),
                "message": e.get("msg", "invalid"),
                "code": e.get("type", "invalid"),
            }
            for e in exc.errors()
        ]
        return problem(422, "VALIDATION_ERROR", "Validation failed", "One or more fields are invalid.", errors=errors)

    @app.exception_handler(StarletteHTTPException)
    async def _http(_: Request, exc: StarletteHTTPException) -> JSONResponse:
        code, title = _HTTP_CODES.get(exc.status_code, ("HTTP_ERROR", "HTTP error"))
        detail = exc.detail if isinstance(exc.detail, str) else None
        return problem(exc.status_code, code, title, detail, headers=getattr(exc, "headers", None))

    @app.exception_handler(Exception)
    async def _unhandled(_: Request, exc: Exception) -> JSONResponse:  # last-resort fallback
        log.exception("unhandled error")
        return internal_error()


def internal_error() -> JSONResponse:
    # Never leak internals; the request_id lets us find the stack trace in the logs.
    return problem(500, "INTERNAL_ERROR", "Internal server error", "Something went wrong on our side.")
