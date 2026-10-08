"""Hourly tick → one fetch per cell in use → recompute every affected user once."""

from datetime import datetime
from typing import Any
from uuid import UUID

import structlog

from lung.domain.geo import cell_center
from lung.integrations.open_meteo import SOURCE
from lung.repositories import air_readings as air_repo
from lung.repositories import places as places_repo
from lung.repositories import refresh_tokens as refresh_repo
from lung.repositories import travel as travel_repo
from lung.services import station_service, warm_service
from lung.services.context import AppContext

log = structlog.get_logger()

FETCH_FRESH_S = 50 * 60  # a cell fetched within this window is not fetched again
FETCH_LOCK_S = 120  # one worker fetches a cell at a time
RECOMPUTE_DELAY_S = 60  # let the other cells of the same tick land first
RECOMPUTE_DEDUPE_S = 5 * 60


def fetch_msg(cell_id: str, at: datetime | None = None) -> dict[str, Any]:
    msg: dict[str, Any] = {"type": "fetch", "cell_id": cell_id}
    if at is not None:
        msg["at"] = at.isoformat()
    return msg


def recompute_msg(user_id: str) -> dict[str, Any]:
    return {"type": "recompute", "user_id": user_id}


async def queue_recompute(ctx: AppContext, user_id: UUID) -> bool:
    """Queue one delayed recompute per user, however many cells change at once."""
    if not await ctx.cache.claim(f"recompute-queued:{user_id}", RECOMPUTE_DEDUPE_S):
        return False
    await ctx.queue.send(
        ctx.settings.sqs_user_url, recompute_msg(str(user_id)), delay_s=RECOMPUTE_DELAY_S
    )
    return True


async def tick(ctx: AppContext, at: datetime) -> int:
    async with ctx.db.session() as s:
        await air_repo.ensure_partitions(s)
        purged = await refresh_repo.purge_expired(s)  # housekeeping rides on the tick
        await travel_repo.purge_old(s)  # recorded travel is kept 7 days
        used = await places_repo.cells_in_use(s)
    # plus popular areas kept warm ahead of demand (warm_areas.yaml)
    warm = (
        warm_service.warm_cells(ctx.settings.cell_resolution_deg) if ctx.settings.warm_areas else ()
    )
    cells = sorted({*used, *warm})
    await ctx.queue.send_many(ctx.settings.sqs_ingest_url, [fetch_msg(c, at) for c in cells])
    if ctx.fires is not None:
        await ctx.queue.send(ctx.settings.sqs_ingest_url, {"type": "fires"})
    log.info("tick", cells=len(cells), in_use=len(used), refresh_tokens_purged=purged)
    return len(cells)


async def fetch(ctx: AppContext, cell_id: str, force: bool = False) -> int:
    """Pull and store one cell. Skips if fetched recently (unless forced) or if another
    worker is fetching it right now; the lock is released on failure so a retry can run."""
    fresh_key, lock_key = f"fetched:{cell_id}", f"fetching:{cell_id}"
    if not force and await ctx.cache.get_json(fresh_key):
        return 0
    if not await ctx.cache.claim(lock_key, FETCH_LOCK_S):
        return 0
    try:
        center = cell_center(cell_id)
        rows = await ctx.air.hourly(center.lat, center.lon)
        source = SOURCE
        if ctx.openaq is not None or ctx.cpcb is not None:
            stations = await station_service.readings_near(ctx, center)
            rows, ratio, used = station_service.apply(rows, center, stations, ctx)
            if used:
                source = station_service.CORRECTED
                log.info("station_corrected", cell_id=cell_id, ratio=round(ratio, 2), stations=used)
        async with ctx.db.session() as s:
            stored = await air_repo.upsert_many(s, cell_id, source, rows)
            users = await places_repo.users_in_cell(s, cell_id)
        await ctx.cache.set_json(fresh_key, 1, FETCH_FRESH_S)
    finally:
        await ctx.cache.delete(lock_key)

    for user_id in users:
        await queue_recompute(ctx, user_id)
    log.info("fetched", cell_id=cell_id, hours=stored, users=len(users))
    return stored
