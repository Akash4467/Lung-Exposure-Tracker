import asyncio
from datetime import UTC, datetime

from fastapi import APIRouter
from fastapi.responses import JSONResponse
from sqlalchemy import text

from lung.api.deps import Ctx
from lung.repositories import air_readings as air_repo
from lung.repositories import places as places_repo
from lung.services import warm_service

router = APIRouter(tags=["health"])


@router.get("/health")
async def health() -> dict[str, str]:
    """Shallow liveness check for Caddy and the load balancer; touches nothing else."""
    return {"status": "ok"}


@router.get("/ready")
async def ready(ctx: Ctx) -> JSONResponse:
    """Deep check: database, cache and queue. 503 if the database or queue is down;
    Valkey being down only degrades (the cache fails open)."""

    async def db() -> bool:
        try:
            async with ctx.db.session() as s:
                await s.execute(text("SELECT 1"))
            return True
        except Exception:
            return False

    db_ok, cache_ok, queue_ok = await asyncio.gather(
        db(), ctx.cache.ping(), ctx.queue.ping(ctx.settings.sqs_user_url)
    )
    checks = {"database": db_ok, "cache": cache_ok, "queue": queue_ok}
    ok = db_ok and queue_ok
    return JSONResponse(
        {"status": "ok" if ok else "unavailable", "checks": checks}, 200 if ok else 503
    )


STALE_AFTER_MIN = 150  # hourly tick + up to 50 min before a cell is re-fetched + slack
STATUS_CACHE_S = 60


@router.get("/status")
async def status(ctx: Ctx) -> JSONResponse:
    """Public, for an outside uptime check: is the API up AND is the air data fresh?

    503 when the database is unreachable or no area has been fetched for 2.5 hours (worker,
    tick or Open-Meteo broken). Says nothing about users; cached for a minute.
    """
    cached = await ctx.cache.get_json("status:public")
    if cached is not None:
        return JSONResponse(cached, 200 if cached["status"] == "ok" else 503)
    now = datetime.now(UTC)  # fetched_at is the database's own now(), not the app clock
    try:
        async with ctx.db.session() as s:
            cells = list(warm_service.warm_cells(ctx.settings.cell_resolution_deg))
            if not ctx.settings.warm_areas or not cells:
                cells = await places_repo.cells_in_use(s, now)
            last = await air_repo.latest_fetch(s, cells) if cells else None
    except Exception:
        return JSONResponse({"status": "unavailable"}, 503)
    # max(0, ...): the database clock can run slightly ahead of this one
    age = None if last is None else max(0, int((now - last).total_seconds() // 60))
    body = {
        "status": "ok" if age is not None and age <= STALE_AFTER_MIN else "stale",
        "air_age_min": age,
    }
    await ctx.cache.set_json("status:public", body, STATUS_CACHE_S)
    return JSONResponse(body, 200 if body["status"] == "ok" else 503)
