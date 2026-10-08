"""One error shape for every failure:  {"error": {"code": "...", "message": "..."}}"""

from typing import Any

import structlog
from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from lung.domain.errors import (
    AppError,
    Conflict,
    Forbidden,
    InvalidInput,
    NotFound,
    TooManyRequests,
    TryLater,
    Unauthorized,
)

log = structlog.get_logger()

STATUS: dict[type[AppError], int] = {
    InvalidInput: 400,
    Unauthorized: 401,
    Forbidden: 403,
    NotFound: 404,
    Conflict: 409,
    TooManyRequests: 429,
    TryLater: 503,
}
HTTP_CODES = {
    400: "bad_request",
    401: "unauthorized",
    403: "forbidden",
    404: "not_found",
    405: "method_not_allowed",
    413: "too_large",
    429: "rate_limited",
}


def error_body(code: str, message: str, details: Any = None) -> dict[str, Any]:
    err: dict[str, Any] = {"code": code, "message": message}
    if details is not None:
        err["details"] = details
    return {"error": err}


def install(app: FastAPI) -> None:
    @app.exception_handler(AppError)
    async def app_error(_: Request, e: AppError) -> JSONResponse:
        status = next((s for cls, s in STATUS.items() if isinstance(e, cls)), 400)
        headers = {}
        if isinstance(e, TooManyRequests | TryLater):
            headers["Retry-After"] = str(e.retry_after_s)
        if status == 401:
            headers["WWW-Authenticate"] = "Bearer"
        return JSONResponse(error_body(e.code, e.message), status, headers=headers)

    @app.exception_handler(RequestValidationError)
    async def validation(_: Request, e: RequestValidationError) -> JSONResponse:
        details = [
            {"field": ".".join(str(p) for p in err["loc"][1:]), "message": err["msg"]}
            for err in e.errors()
        ]
        first = details[0] if details else {"field": "", "message": "invalid request"}
        msg = f"{first['field']}: {first['message']}" if first["field"] else first["message"]
        return JSONResponse(error_body("validation_failed", msg, details), 400)

    @app.exception_handler(StarletteHTTPException)
    async def http_error(_: Request, e: StarletteHTTPException) -> JSONResponse:
        code = HTTP_CODES.get(e.status_code, "error")
        return JSONResponse(
            error_body(code, str(e.detail)), e.status_code, headers=getattr(e, "headers", None)
        )

    @app.exception_handler(Exception)
    async def unexpected(_: Request, e: Exception) -> JSONResponse:
        log.exception("unhandled_error")
        return JSONResponse(error_body("internal_error", "something went wrong"), 500)
