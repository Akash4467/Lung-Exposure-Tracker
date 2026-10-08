"""Smoke risk from fires upwind (NASA FIRMS).

- refresh(): every few hours the worker pulls the last day of fire detections over the area
  around everyone's places (plus a margin), stores them, and drops detections older than a week.
- upwind_count(): for a place and tomorrow, the wind direction it will mostly come from
  (speed-weighted vector mean of the hourly wind forecast for that cell) and the number of
  non-low-confidence fires within `fire_radius_km` in that direction (± half angle) in the
  last `fire_window_h` hours. The engine turns that count into none / low / medium / high.

Without FIRMS_MAP_KEY nothing is fetched and the count is always 0.
"""

import math
from datetime import datetime, timedelta

import structlog

from lung.domain.geo import cell_center
from lung.repositories import air_readings as air_repo
from lung.repositories import fires as fires_repo
from lung.repositories import places as places_repo
from lung.services.context import AppContext

log = structlog.get_logger()

FETCH_DAYS = 1
MARGIN_DEG = 5.0  # ~500 km: smoke travels far
KEEP = timedelta(days=7)
REFRESH_KEY = "fires:refreshed"
REFRESH_EVERY_S = 3 * 3600  # FIRMS near-real-time data lands every few hours


def wind_from(rows: list[tuple[float | None, float | None]]) -> float | None:
    """Speed-weighted vector mean of (speed m/s, direction the wind comes FROM, degrees)."""
    x = y = 0.0
    for speed, deg in rows:
        if speed is None or deg is None:
            continue
        x += speed * math.sin(math.radians(deg))
        y += speed * math.cos(math.radians(deg))
    if math.hypot(x, y) < 0.3:  # calm or no data: no meaningful direction
        return None
    return (math.degrees(math.atan2(x, y)) + 360) % 360


async def refresh(ctx: AppContext, force: bool = False) -> int:
    if ctx.fires is None:
        return 0
    if not force and not await ctx.cache.claim(REFRESH_KEY, REFRESH_EVERY_S):
        return 0
    async with ctx.db.session() as s:
        cells = await places_repo.cells_in_use(s)
    if not cells:
        return 0
    pts = [cell_center(c) for c in cells]
    west = max(-180.0, min(p.lon for p in pts) - MARGIN_DEG)
    east = min(180.0, max(p.lon for p in pts) + MARGIN_DEG)
    south = max(-90.0, min(p.lat for p in pts) - MARGIN_DEG)
    north = min(90.0, max(p.lat for p in pts) + MARGIN_DEG)
    detections = await ctx.fires.fires(west, south, east, north, FETCH_DAYS)
    async with ctx.db.session() as s:
        stored = await fires_repo.add_many(s, detections)
        purged = await fires_repo.purge_before(s, ctx.clock() - KEEP)
    log.info("fires_refreshed", detections=stored, purged=purged)
    return stored


async def upwind_count(ctx: AppContext, cell: str, day_start: datetime, day_end: datetime) -> int:
    """Upwind fire detections that matter for `cell` on the day [day_start, day_end)."""
    if ctx.fires is None:
        return 0
    fc = ctx.cfg.forecast
    async with ctx.db.session() as s:
        hours = await air_repo.hourly_for_point(s, cell, day_start, day_end)
        direction = wind_from([(h["wind_speed"], h["wind_dir"]) for h in hours])
        if direction is None:
            return 0
        center = cell_center(cell)
        return await fires_repo.count_upwind(
            s,
            center.lat,
            center.lon,
            fc.fire_radius_km,
            ctx.clock() - timedelta(hours=fc.fire_window_h),
            direction,
            fc.fire_upwind_half_angle_deg,
        )
