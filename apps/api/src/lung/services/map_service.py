"""The map: PM2.5 anywhere in the world, for browsing, searching places and planning trips.

Not tied to the user's cells. Values come straight from Open-Meteo's global air-quality model
(about 10-40 km per grid square, so city-level, not street-level) and are cached in Valkey so
scrolling around doesn't spend the free daily quota.

- grid: the visible area as up to ~11 x 11 points, coarser when zoomed out.
- place: one place, hour by hour for yesterday and the next days, plus each local day's
  average and its cleanest hours.
"""

import asyncio
import math
from datetime import UTC, datetime, timedelta
from typing import Any

from lung.domain.errors import InvalidInput
from lung.services.context import AppContext

GRID_STEPS = (0.1, 0.25, 0.5, 1.0, 2.0, 5.0, 10.0, 15.0, 30.0)  # degrees, finest first
MAX_PER_SIDE = 11
GRID_TTL_S = 30 * 60  # the model updates hourly; half an hour is fresh enough to browse
PLACE_TTL_S = 30 * 60
PLACE_CELL = 0.05  # forecasts are cached per ~5 km square
FORECAST_DAYS = 5
_fetch_lock = asyncio.Lock()


def grid_step(south: float, west: float, north: float, east: float) -> float:
    """The finest step that keeps the grid at or under MAX_PER_SIDE points on each side."""
    span = max(north - south, east - west)
    for step in GRID_STEPS:
        if span / step <= MAX_PER_SIDE - 1:
            return step
    return GRID_STEPS[-1]


def grid_points(
    south: float, west: float, north: float, east: float
) -> tuple[float, list[tuple[float, float]]]:
    """Points on a fixed world lattice (multiples of the step), so neighbouring views share
    cached points."""
    if not (-90 <= south < north <= 90 and -180 <= west < east <= 180):
        raise InvalidInput("the area must be south < north and west < east", "bad_bounds")
    step = grid_step(south, west, north, east)
    lat0 = math.floor(south / step) * step
    lon0 = math.floor(west / step) * step
    pts: list[tuple[float, float]] = []
    lat = lat0
    while lat <= north + step / 2 and len(pts) < 400:
        lon = lon0
        while lon <= east + step / 2:
            if -90 <= lat <= 90 and -180 <= lon <= 180:
                pts.append((round(lat, 4), round(lon, 4)))
            lon += step
        lat += step
    return step, pts


def _grid_key(step: float, lat: float, lon: float) -> str:
    return f"map:grid:{step}:{lat:.4f}:{lon:.4f}"


async def grid(
    ctx: AppContext, south: float, west: float, north: float, east: float
) -> dict[str, Any]:
    step, pts = grid_points(south, west, north, east)
    keys = [_grid_key(step, lat, lon) for lat, lon in pts]
    cached = await asyncio.gather(*(ctx.cache.get_json(k) for k in keys))
    values: dict[int, float | None] = {i: c["pm25"] for i, c in enumerate(cached) if c is not None}
    missing = [i for i in range(len(pts)) if i not in values]
    if missing:
        async with _fetch_lock:  # one batch at a time towards Open-Meteo
            fresh = await ctx.air.current_many([pts[i] for i in missing])
        for i, v in zip(missing, fresh, strict=False):
            values[i] = v
            await ctx.cache.set_json(keys[i], {"pm25": v}, GRID_TTL_S)
    return {
        "step": step,
        "points": [
            {"lat": lat, "lon": lon, "pm25": round(v, 1)}
            for i, (lat, lon) in enumerate(pts)
            if (v := values.get(i)) is not None
        ],
        "source": "open_meteo",
        "estimated": True,
    }


def _snap(v: float) -> float:
    return round(round(v / PLACE_CELL) * PLACE_CELL, 4)


async def place(ctx: AppContext, lat: float, lon: float) -> dict[str, Any]:
    if not (-90 <= lat <= 90 and -180 <= lon <= 180):
        raise InvalidInput("lat/lon out of range", "bad_coordinates")
    lat_s, lon_s = _snap(lat), _snap(lon)
    key = f"map:place:{lat_s}:{lon_s}"
    cached = await ctx.cache.get_json(key)
    if cached is not None:
        return cached  # type: ignore[no-any-return]

    fc = await ctx.air.place_forecast(lat_s, lon_s, FORECAST_DAYS)
    now = ctx.clock().replace(minute=0, second=0, microsecond=0)
    offset = timedelta(seconds=fc.utc_offset_s)
    current = next((h for h in fc.hours if h[0] == now), None) or min(
        fc.hours, key=lambda h: abs((h[0] - now).total_seconds()), default=None
    )
    days: dict[str, list[tuple[datetime, float]]] = {}
    for hour, p25, _ in fc.hours:
        if hour < now - timedelta(hours=1):
            continue
        days.setdefault((hour + offset).date().isoformat(), []).append((hour, p25))
    out = {
        "lat": lat_s,
        "lon": lon_s,
        "utc_offset_s": fc.utc_offset_s,
        "now": {"pm25": round(current[1], 1), "pm10": current[2], "hour": current[0].isoformat()}
        if current
        else None,
        "hours": [
            {"hour": h.isoformat(), "pm25": round(p, 1), "is_forecast": h > now}
            for h, p, _ in fc.hours
        ],
        "days": [
            {
                "date": d,
                "avg_pm25": round(sum(p for _, p in hrs) / len(hrs), 1),
                "max_pm25": round(max(p for _, p in hrs), 1),
                # the three cleanest daytime hours (7 am - 9 pm local) for being outside
                "best_hours": [
                    h.isoformat()
                    for h, _ in sorted(
                        (x for x in hrs if 7 <= (x[0] + offset).hour <= 21), key=lambda x: x[1]
                    )[:3]
                ],
            }
            for d, hrs in days.items()
            if len(hrs) >= 6
        ],
        "source": "open_meteo",
        "estimated": True,
        "fetched_at": datetime.now(UTC).isoformat(),
    }
    await ctx.cache.set_json(key, out, PLACE_TTL_S)
    return out
