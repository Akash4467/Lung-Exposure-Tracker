"""Tomorrow: the same compute() on forecast readings, plus the hours to avoid outdoors.

Two refinements on top of the raw model forecast:
- nowcast: the model's error right now (station or sensor vs model) carries into the next
  hours and fades with time constant tau;
- fire risk: upwind fire detections raise a smoke-risk flag. The PM2.5 uplift per fire is in
  config but 0 until it can be fitted to real data, so the flag never invents a number.
"""

import math
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta
from zoneinfo import ZoneInfo

from lung.engine.config import EngineConfig
from lung.engine.day import build_day
from lung.engine.dose import MissingReadingError, outdoor_pm25
from lung.engine.models import DayPlan, FireRisk, Profile, Readings, Result, Segment
from lung.engine.score import compute


@dataclass(frozen=True)
class HourRisk:
    start: datetime  # local hour start, timezone-aware
    pm25: float  # outdoor, at home


@dataclass(frozen=True)
class Forecast:
    result: Result
    hours: list[HourRisk]
    worst_hours: list[HourRisk]  # highest outdoor PM2.5
    best_outdoor_hours: list[HourRisk]  # lowest, within waking daytime
    fire_risk: FireRisk


def nowcast(
    forecast_by_hour: Mapping[datetime, float],
    latest_hour: datetime,
    latest_ratio: float,
    cfg: EngineConfig,
) -> dict[datetime, float]:
    """Carry the current model error (observed / model at `latest_hour`) into later hours.

    The log of the ratio decays as exp(-lead / tau), so in a few hours the raw forecast
    takes over again. Hours at or before `latest_hour` are returned unchanged.
    """
    fc = cfg.forecast
    if latest_ratio <= 0:
        return dict(forecast_by_hour)
    limit = math.log(fc.nowcast_max_ratio)
    log_ratio = max(-limit, min(limit, math.log(latest_ratio)))
    out: dict[datetime, float] = {}
    for hour, value in forecast_by_hour.items():
        lead_h = (hour - latest_hour).total_seconds() / 3600
        if lead_h <= 0:
            out[hour] = value
        else:
            out[hour] = value * math.exp(log_ratio * math.exp(-lead_h / fc.nowcast_tau_h))
    return out


def fire_risk(upwind_fires: int, cfg: EngineConfig) -> FireRisk:
    t = cfg.forecast.fire_risk_upwind_count
    if upwind_fires >= t["high"]:
        return "high"
    if upwind_fires >= t["medium"]:
        return "medium"
    if upwind_fires >= t["low"]:
        return "low"
    return "none"


def _with_fire_uplift(readings: Readings, upwind_fires: int, cfg: EngineConfig) -> Readings:
    k = cfg.forecast.fire_pm25_uplift_per_fire
    if k == 0 or upwind_fires == 0:
        return readings
    scale = 1 + k * upwind_fires
    return {cell: {h: v * scale for h, v in hours.items()} for cell, hours in readings.items()}


def forecast(
    profile: Profile,
    local_date: date,
    plan: DayPlan,
    readings: Readings,
    cfg: EngineConfig,
    *,
    upwind_fires: int = 0,
    top_n: int = 3,
    daytime: tuple[int, int] = (6, 21),
) -> Forecast:
    readings = _with_fire_uplift(readings, upwind_fires, cfg)
    result = compute(profile, build_day(local_date, plan, cfg), readings, cfg)

    # Local hours need not line up with UTC reading hours (India is UTC+5:30), so each
    # local hour is time-weighted across the UTC hours it overlaps.
    tz = ZoneInfo(plan.tz)
    midnight = datetime.combine(local_date, time(0), tzinfo=tz)
    hours: list[HourRisk] = []
    for h in range(24):
        local = midnight + timedelta(hours=h)
        probe = Segment(
            place="home",
            activity="light",
            start=local,
            end=local + timedelta(hours=1),
            cell_id=plan.home_cell,
            factor=1.0,
        )
        try:
            hours.append(HourRisk(start=local, pm25=outdoor_pm25(probe, readings)))
        except MissingReadingError:
            continue

    worst = sorted(hours, key=lambda r: r.pm25, reverse=True)[:top_n]
    lo, hi = daytime
    day_hours = [r for r in hours if lo <= r.start.hour < hi]
    best = sorted(day_hours, key=lambda r: r.pm25)[:top_n]
    return Forecast(
        result=result,
        hours=hours,
        worst_hours=worst,
        best_outdoor_hours=best,
        fire_risk=fire_risk(upwind_fires, cfg),
    )
