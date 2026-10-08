"""Place search for the app, through our server so it is fast and polite:

- answers are cached (searches 7 days, reverse lookups 30 days), so repeats are instant;
- Nominatim gets at most 1 request a second from us (its usage policy), shared across all
  users through Valkey; if a slot doesn't free up quickly, or Nominatim fails, Photon answers.
"""

import asyncio
import re
from dataclasses import asdict
from typing import Any

import structlog

from lung.domain.errors import InvalidInput
from lung.integrations.geocoder import GeoPlace
from lung.services.context import AppContext

log = structlog.get_logger()

SEARCH_TTL_S = 7 * 24 * 3600
REVERSE_TTL_S = 30 * 24 * 3600
SLOT_KEY = "geo:nominatim-slot"
SLOT_S = 1  # Nominatim: max 1 request per second
SLOT_WAIT_S = 2.5
LIMIT = 6


async def _nominatim_slot(ctx: AppContext) -> bool:
    """Wait (briefly) for our once-a-second turn at Nominatim."""
    deadline = asyncio.get_running_loop().time() + SLOT_WAIT_S
    while True:
        if await ctx.cache.claim(SLOT_KEY, SLOT_S):
            return True
        if asyncio.get_running_loop().time() >= deadline:
            return False
        await asyncio.sleep(0.25)


def _norm(q: str) -> str:
    return re.sub(r"\s+", " ", q.strip().lower())


def _near_key(near: tuple[float, float] | None) -> str:
    return f"{round(near[0])},{round(near[1])}" if near else "-"


async def search(ctx: AppContext, q: str, near: tuple[float, float] | None) -> list[dict[str, Any]]:
    query = _norm(q)
    if len(query) < 3:
        return []
    if len(query) > 120:
        raise InvalidInput("search text is too long", "bad_query")
    key = f"geo:s:{_near_key(near)}:{query}"
    cached = await ctx.cache.get_json(key)
    if cached is not None:
        return cached  # type: ignore[no-any-return]

    if ctx.geocoder is None:
        return []
    places: list[GeoPlace] = []
    if await _nominatim_slot(ctx):
        try:
            places = await ctx.geocoder.nominatim_search(q.strip(), near, LIMIT)
        except Exception as e:
            log.warning("geocode_nominatim_failed", error=str(e))
    if not places:
        try:
            places = await ctx.geocoder.photon_search(q.strip(), near, LIMIT)
        except Exception as e:
            log.warning("geocode_photon_failed", error=str(e))
            return []
    out = [asdict(p) for p in places]
    await ctx.cache.set_json(key, out, SEARCH_TTL_S)
    return out


async def reverse(ctx: AppContext, lat: float, lon: float) -> dict[str, Any] | None:
    key = f"geo:r:{lat:.4f},{lon:.4f}"
    cached = await ctx.cache.get_json(key)
    if cached is not None:
        return cached.get("place")  # type: ignore[no-any-return]
    if ctx.geocoder is None:
        return None
    place: GeoPlace | None = None
    if await _nominatim_slot(ctx):
        try:
            place = await ctx.geocoder.nominatim_reverse(lat, lon)
        except Exception as e:
            log.warning("reverse_nominatim_failed", error=str(e))
    out = asdict(place) if place else None
    await ctx.cache.set_json(key, {"place": out}, REVERSE_TTL_S)
    return out
