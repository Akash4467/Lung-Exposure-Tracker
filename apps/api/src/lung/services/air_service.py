"""Hourly air for any point, for the app's map and charts. Read from our own store."""

from datetime import timedelta
from typing import Any

from lung.domain.errors import InvalidInput, TryLater
from lung.domain.geo import cell_id
from lung.repositories import air_readings as air_repo
from lung.services.context import AppContext
from lung.services.ingest_service import fetch_msg

CACHE_S = 10 * 60


async def hourly_for_point(ctx: AppContext, lat: float, lon: float) -> dict[str, Any]:
    if not (-90 <= lat <= 90 and -180 <= lon <= 180):
        raise InvalidInput("lat/lon out of range", "bad_coordinates")
    cell = cell_id(lat, lon, ctx.settings.cell_resolution_deg)
    key = f"air:{cell}"
    cached = await ctx.cache.get_json(key)
    if cached is not None:
        return cached  # type: ignore[no-any-return]

    now = ctx.clock().replace(minute=0, second=0, microsecond=0)
    async with ctx.db.session() as s:
        rows = await air_repo.hourly_for_point(
            s, cell, now - timedelta(hours=24), now + timedelta(hours=48)
        )
    if not rows:
        # Not a cell anyone uses yet: fetch it once so the next call has data.
        await ctx.queue.send(ctx.settings.sqs_ingest_url, fetch_msg(cell) | {"force": True})
        raise TryLater("air data for this area is loading", 60)
    out = {
        "cell_id": cell,
        "source": rows[-1]["source"],
        "hours": [
            {
                "hour": r["hour"].isoformat(),
                "pm25": r["pm25"],
                "pm10": r["pm10"],
                "wind_speed": r["wind_speed"],
                "wind_dir": r["wind_dir"],
                "is_forecast": r["hour"] > now,
            }
            for r in rows
        ],
        "estimated": True,
    }
    await ctx.cache.set_json(key, out, CACHE_S)
    return out
