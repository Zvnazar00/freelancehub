import logging
import time
import uuid
from collections.abc import Awaitable, Callable

from fastapi import FastAPI, Request, Response
from fastapi.middleware.cors import CORSMiddleware

from app.api import errors
from app.api.v1.router import api_router
from app.core.config import Settings, get_settings
from app.core.logging import configure_logging, request_id_var
from app.core.rate_limit import RateLimiter

API_PREFIX = "/api/v1"
log = logging.getLogger("app.request")


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or get_settings()
    configure_logging(settings.log_level)

    app = FastAPI(
        title=settings.app_name,
        version="0.1.0",
        openapi_url=None if settings.is_production else f"{API_PREFIX}/openapi.json",
        docs_url=None if settings.is_production else "/docs",
        redoc_url=None,
    )
    app.state.rate_limiter = RateLimiter()

    if settings.cors_origins:
        app.add_middleware(
            CORSMiddleware,
            allow_origins=settings.cors_origins,
            allow_methods=["*"],
            allow_headers=["Authorization", "Content-Type", "Idempotency-Key"],
            expose_headers=["X-Request-ID", "Idempotent-Replayed", "Content-Disposition"],
        )

    @app.middleware("http")
    async def request_context(request: Request, call_next: Callable[[Request], Awaitable[Response]]) -> Response:
        incoming = request.headers.get("x-request-id", "")
        request_id = incoming if 0 < len(incoming) <= 64 and incoming.isascii() else uuid.uuid4().hex
        token = request_id_var.set(request_id)
        started = time.perf_counter()
        try:
            try:
                response = await call_next(request)
            except Exception:
                # Handled here (not only in the outermost handler) so the 500 still carries the request ID.
                logging.getLogger("app.errors").exception("unhandled error")
                response = errors.internal_error()
            response.headers["X-Request-ID"] = request_id
            # Path only: query strings and bodies may contain sensitive data.
            log.info(
                "request",
                extra={
                    "data": {
                        "method": request.method,
                        "path": request.url.path,
                        "status": response.status_code,
                        "ms": round((time.perf_counter() - started) * 1000, 1),
                    }
                },
            )
        finally:
            request_id_var.reset(token)
        return response

    errors.install(app)
    app.include_router(api_router, prefix=API_PREFIX)
    return app


app = create_app()
