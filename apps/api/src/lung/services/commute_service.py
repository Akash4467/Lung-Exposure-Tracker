"""The commute on the map: the stored route, coloured by roadside PM2.5 at the times the
person travels, and what each way of travelling would mean on that same route.

"Per hour of travel" compares vehicles fairly on air alone: how much outside air gets in
(commute_factor), the mask, and how hard the body is working (breathing rate). Trip length
differs by mode, so the app shows it as a rate, not a day total.
"""

from datetime import UTC, datetime, timedelta
from datetime import time as dtime
from typing import Any
from uuid import UUID
from zoneinfo import ZoneInfo

from lung.domain.errors import NotFound
from lung.engine.dose import breathing_rate
from lung.repositories import air_readings as air_repo
from lung.repositories import routes as routes_repo
from lung.services.context import AppContext
from lung.services.plan import ProfileIncompleteError, load_inputs


def _hour_utc(day: Any, t: dtime, tz: str) -> datetime:
    local = datetime.combine(day, t, tzinfo=ZoneInfo(tz))
    return local.astimezone(UTC).replace(minute=0, second=0, microsecond=0)


async def commute_view(ctx: AppContext, user_id: UUID) -> dict[str, Any]:
    cfg = ctx.cfg
    async with ctx.db.session() as s:
        try:
            inputs = await load_inputs(s, user_id, ctx.settings.cell_resolution_deg, ctx.clock())
        except ProfileIncompleteError as e:
            raise NotFound("finish onboarding first", "profile_incomplete") from e
        pts = await routes_repo.points(s, user_id)
        meta = await routes_repo.meta(s, user_id)
        today = ctx.clock().astimezone(ZoneInfo(inputs.tz)).date()
        sc = inputs.schedule
        morning = _hour_utc(today, sc.leave_home, inputs.tz)
        evening = _hour_utc(today, sc.leave_office, inputs.tz)
        cells = sorted({p.cell_id for p in pts})
        readings = await air_repo.pm25_for(
            s, cells, morning - timedelta(hours=1), evening + timedelta(hours=2)
        )

    def leg(hour: datetime, reverse: bool) -> dict[str, Any]:
        out: list[dict[str, Any]] = []
        for p in reversed(pts) if reverse else pts:
            base = readings.get(p.cell_id, {}).get(hour)
            road = cfg.road_factor.get(p.road_class, 1.0)
            out.append(
                {
                    "lat": p.lat,
                    "lon": p.lon,
                    "road_class": p.road_class,
                    "pm25": round(base * road, 1) if base is not None else None,
                }
            )
        known: list[float] = [x["pm25"] for x in out if x["pm25"] is not None]
        return {
            "depart": hour.isoformat(),
            "avg_pm25": round(sum(known) / len(known), 1) if known else None,
            "points": out,
        }

    am, pm = leg(morning, False), leg(evening, True)
    avg = am["avg_pm25"] if am["avg_pm25"] is not None else pm["avg_pm25"]
    mask = cfg.mask_factor.get(sc.commute_mask, 1.0)
    modes = []
    if avg is not None:
        for mode, factor in cfg.commute_factor.items():
            inside = avg * factor * mask
            rate = breathing_rate(inputs.profile, cfg.commute_activity[mode], cfg)
            modes.append(
                {
                    "mode": mode,
                    "inside_pm25": round(inside, 1),
                    "breathing_m3_per_h": round(rate, 2),
                    "ug_per_hour": round(inside * rate, 1),
                    "current": mode == sc.commute_mode,
                }
            )
        modes.sort(key=lambda m: m["ug_per_hour"])
    return {
        "mode": sc.commute_mode,
        "mask": sc.commute_mask,
        "source": meta[0] if meta else None,
        "distance_km": round(meta[1], 1) if meta else None,
        "home": {"lat": inputs.home.lat, "lon": inputs.home.lon, "label": inputs.home.label},
        "office": {
            "lat": inputs.office.lat,
            "lon": inputs.office.lon,
            "label": inputs.office.label,
        },
        "morning": am,
        "evening": pm,
        "modes": modes,
        "estimated": True,
    }
