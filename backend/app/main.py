"""FastAPI application factory."""

from __future__ import annotations

import time
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware

from app.api.errors import install_error_handlers
from app.api.v1.router import api_router
from app.container import Container, set_container
from app.core.config import settings
from app.core.logging import configure_logging, get_logger, new_request_id, set_request_context

logger = get_logger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    configure_logging()
    container = Container()
    app.state.container = container
    set_container(container)
    await container.startup()
    try:
        yield
    finally:
        await container.shutdown()
        set_container(None)
        logger.info("buttlr stopped")


def create_app() -> FastAPI:
    configure_logging()
    app = FastAPI(
        title=f"{settings.app_name} API",
        version=settings.version,
        description=(
            "Buttlr — an AI workforce platform. Describe an AI employee, give it scoped access "
            "to real tools, decide what it may do on its own, and supervise the rest."
        ),
        docs_url="/docs",
        openapi_url="/openapi.json",
        lifespan=lifespan,
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_origin_regex=r"https://.*\.vercel\.app",
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
        expose_headers=["X-Request-ID"],
    )

    @app.middleware("http")
    async def request_context(request: Request, call_next):
        request_id = request.headers.get("X-Request-ID") or new_request_id()
        set_request_context(request_id=request_id)
        started = time.perf_counter()
        response = await call_next(request)
        response.headers["X-Request-ID"] = request_id
        duration_ms = int((time.perf_counter() - started) * 1000)
        if request.url.path not in ("/health", "/api/v1/health"):
            logger.info(
                "%s %s -> %s (%dms)",
                request.method,
                request.url.path,
                response.status_code,
                duration_ms,
            )
        return response

    install_error_handlers(app)
    app.include_router(api_router, prefix=settings.api_v1_prefix)

    @app.get("/", include_in_schema=False)
    async def root() -> dict[str, str]:
        return {
            "name": settings.app_name,
            "description": "An AI Workforce Operating System.",
            "version": settings.version,
            "docs": "/docs",
        }

    return app


app = create_app()
