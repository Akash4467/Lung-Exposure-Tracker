"""Builds the FastAPI app and mounts the routers."""

import time
import uuid
from collections.abc import AsyncIterator, Awaitable, Callable
from contextlib import asynccontextmanager

import httpx
import structlog
from fastapi import FastAPI, Request, Response
from fastapi.middleware.cors import CORSMiddleware

from lung.api import errors, health
from lung.api.v1 import activity, auth, geo, map, me, meta, scores, tracks, trips
from lung.infra.logging import configure_logging
from lung.services.context import AppContext, build_context, close_context
from lung.settings import get_settings

log = structlog.get_logger()


def create_app(ctx: AppContext | None = None) -> FastAPI:
    """`ctx` lets tests inject a context with fakes; normally it's built at startup."""
    settings = ctx.settings if ctx else get_settings()
    configure_logging(settings.log_level, json_output=settings.is_production)

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        if ctx is not None:
            app.state.ctx = ctx
            yield
            return
        async with httpx.AsyncClient(timeout=settings.http_timeout_s) as http:
            app.state.ctx = await build_context(settings, http)
            try:
                yield
            finally:
                await close_context(app.state.ctx)

    app = FastAPI(
        title="Lung Exposure Tracker API",
        version="0.1.0",
        lifespan=lifespan,
        # No public schema browser in production.
        docs_url=None if settings.is_production else "/docs",
        redoc_url=None,
        openapi_url=None if settings.is_production else "/openapi.json",
    )
    if ctx is not None:
        app.state.ctx = ctx

    @app.middleware("http")
    async def request_context(
        request: Request, call_next: Callable[[Request], Awaitable[Response]]
    ) -> Response:
        rid = request.headers.get("x-request-id") or uuid.uuid4().hex
        structlog.contextvars.clear_contextvars()
        structlog.contextvars.bind_contextvars(request_id=rid)
        start = time.perf_counter()
        response = await call_next(request)
        response.headers["X-Request-ID"] = rid
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["Cache-Control"] = "no-store"
        if request.url.path not in ("/health", "/ready"):
            # Method, path and status only: never bodies, tokens or query strings.
            log.info(
                "request",
                method=request.method,
                path=request.url.path,
                status=response.status_code,
                ms=round((time.perf_counter() - start) * 1000, 1),
            )
        return response

    if settings.cors_origins:
        app.add_middleware(
            CORSMiddleware,
            allow_origins=settings.cors_origins,
            allow_methods=["GET", "POST", "PUT", "DELETE"],
            allow_headers=["Authorization", "Content-Type", "X-Request-ID"],
        )
    errors.install(app)
    for router in (
        health.router,
        auth.router,
        me.router,
        activity.router,
        scores.router,
        map.router,
        geo.router,
        trips.router,
        tracks.router,
        meta.router,
    ):
        app.include_router(router)
    return app


app = create_app()
