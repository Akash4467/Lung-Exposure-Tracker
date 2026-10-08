"""Bend the model's PM2.5 towards nearby official monitors (OpenAQ, CPCB).

When a cell's model data is fetched:
1. collect official station readings within `air_correction.radius_km` that are at most
   STATION_MAX_AGE old (OpenAQ per cell; CPCB from one shared India-wide list);
2. compare each with the model at the reading's hour → the engine's `correct()` gives one
   multiplier (1/distance² weights, trust grows with nearby stations, capped ×¼…×4);
3. apply it to the cell's hours, fading with time from the reading:
   factor(h) = ratio ^ exp(-|h - t| / nowcast_tau_h)
   so the hours around "now" follow the stations and the far forecast stays as modelled.
Corrected rows are stored with source "open_meteo+stations".

Without OPENAQ_API_KEY and CPCB_API_KEY nothing changes.
"""

import math
from dataclasses import replace
from datetime import datetime, timedelta

import structlog

from lung.domain.air import HourlyAir
from lung.domain.geo import LatLon, haversine_km
from lung.engine.airdata import StationObs, correct
from lung.integrations.stations import StationReading
from lung.services.context import AppContext

log = structlog.get_logger()

STATION_MAX_AGE = timedelta(hours=3)
OPENAQ_TTL_S = 30 * 60
CPCB_TTL_S = 30 * 60
CORRECTED = "open_meteo+stations"


def _ser(r: StationReading) -> dict[str, object]:
    return {
        "lat": r.lat,
        "lon": r.lon,
        "pm25": r.pm25,
        "at": r.at.isoformat(),
        "provider": r.provider,
        "name": r.name,
    }


def _de(d: dict[str, object]) -> StationReading:
    return StationReading(
        lat=float(d["lat"]),  # type: ignore[arg-type]
        lon=float(d["lon"]),  # type: ignore[arg-type]
        pm25=float(d["pm25"]),  # type: ignore[arg-type]
        at=datetime.fromisoformat(str(d["at"])),
        provider=str(d["provider"]),
        name=str(d["name"]),
    )


async def readings_near(ctx: AppContext, center: LatLon) -> list[StationReading]:
    radius = ctx.cfg.air_correction.radius_km
    now = ctx.clock()
    found: list[StationReading] = []
    if ctx.openaq is not None:
        key = f"stations:openaq:{center.lat:.1f},{center.lon:.1f}"
        cached = await ctx.cache.get_json(key)
        if cached is None:
            try:
                got = await ctx.openaq.near(center.lat, center.lon, radius, STATION_MAX_AGE, now)
            except Exception as e:
                log.warning("openaq_failed", error=str(e))
                got = []
            cached = [_ser(r) for r in got]
            await ctx.cache.set_json(key, cached, OPENAQ_TTL_S)
        found.extend(_de(d) for d in cached)
    if ctx.cpcb is not None:
        cached = await ctx.cache.get_json("stations:cpcb")
        if cached is None:
            try:
                got = await ctx.cpcb.all_pm25()
            except Exception as e:
                log.warning("cpcb_failed", error=str(e))
                got = []
            cached = [_ser(r) for r in got]
            await ctx.cache.set_json("stations:cpcb", cached, CPCB_TTL_S)
        found.extend(
            r for r in map(_de, cached) if haversine_km(center, LatLon(r.lat, r.lon)) <= radius
        )
    return [r for r in found if now - r.at <= STATION_MAX_AGE and r.pm25 >= 0]


def apply(
    rows: list[HourlyAir], center: LatLon, readings: list[StationReading], ctx: AppContext
) -> tuple[list[HourlyAir], float, int]:
    """Corrected rows, the multiplier at the station time, and how many stations were used."""
    if not rows or not readings:
        return rows, 1.0, 0
    by_hour = {r.hour: r.pm25 for r in rows}
    obs: list[StationObs] = []
    times: list[datetime] = []
    for s in readings:
        hour = s.at.replace(minute=0, second=0, microsecond=0)
        model = by_hour.get(hour)
        if model is None or model <= 0:
            continue
        obs.append(StationObs(haversine_km(center, LatLon(s.lat, s.lon)), s.pm25, model))
        times.append(hour)
    if not obs:
        return rows, 1.0, 0
    anchor = max(times)
    model_now = by_hour[anchor]
    result = correct(model_now, obs, ctx.cfg)
    if result.stations_used == 0 or result.ratio == 1.0:
        return rows, 1.0, 0
    log_ratio = math.log(result.ratio)
    tau = ctx.cfg.forecast.nowcast_tau_h
    out = []
    for r in rows:
        lag_h = abs((r.hour - anchor).total_seconds()) / 3600
        out.append(replace(r, pm25=r.pm25 * math.exp(log_ratio * math.exp(-lag_h / tau))))
    return out, result.ratio, result.stations_used
