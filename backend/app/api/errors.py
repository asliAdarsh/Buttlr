"""Error handling.

Every failure reaches the client in one shape: ``{"error": {code, message, details, request_id}}``.
Messages are written for users; technical detail stays in the logs.
"""

from __future__ import annotations

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.core.errors import ButtlrError
from app.core.logging import current_request_id, get_logger

logger = get_logger(__name__)


def install_error_handlers(app: FastAPI) -> None:
    @app.exception_handler(ButtlrError)
    async def _buttlr_error(_: Request, exc: ButtlrError) -> JSONResponse:
        if exc.status_code >= 500:
            logger.warning("handled error %s: %s", exc.code, exc.message)
        return JSONResponse(
            status_code=exc.status_code,
            content={"error": exc.to_payload(current_request_id())},
        )

    @app.exception_handler(RequestValidationError)
    async def _validation_error(_: Request, exc: RequestValidationError) -> JSONResponse:
        details = [
            {"field": ".".join(str(p) for p in error.get("loc", [])), "message": error.get("msg", "")}
            for error in exc.errors()[:10]
        ]
        return JSONResponse(
            status_code=422,
            content={
                "error": {
                    "code": "validation_error",
                    "message": "Some of the information sent was not valid.",
                    "details": {"fields": details},
                    "request_id": current_request_id(),
                }
            },
        )

    @app.exception_handler(StarletteHTTPException)
    async def _http_error(_: Request, exc: StarletteHTTPException) -> JSONResponse:
        message = exc.detail if isinstance(exc.detail, str) else "Request failed."
        return JSONResponse(
            status_code=exc.status_code,
            content={
                "error": {
                    "code": f"http_{exc.status_code}",
                    "message": message,
                    "details": {},
                    "request_id": current_request_id(),
                }
            },
        )

    @app.exception_handler(Exception)
    async def _unhandled(request: Request, exc: Exception) -> JSONResponse:
        logger.exception("unhandled error on %s %s", request.method, request.url.path)
        return JSONResponse(
            status_code=500,
            content={
                "error": {
                    "code": "internal_error",
                    "message": "Something went wrong on our side. Please try again.",
                    "details": {},
                    "request_id": current_request_id(),
                }
            },
        )
