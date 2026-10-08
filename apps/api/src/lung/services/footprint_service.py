"""The person's commute footprint (estimated CO2), for the Trends card and its detail screen.

Built from what we already know: the declared way of commuting, office days and the stored
commute route's length; plus, for people who record trips, the last 7 days of recorded legs.
"""

from datetime import timedelta
from typing import Any
from uuid import UUID

from lung.engine import footprint as fp
from lung.infra.engine_config import load_footprint
from lung.repositories import routes as routes_repo
from lung.repositories import schedules as schedules_repo
from lung.repositories import travel as travel_repo
from lung.services.context import AppContext

RECORDED_DAYS = 7


def _commute_json(c: fp.Commute) -> dict[str, Any]:
    s = c.suggestion
    return {
        "mode": c.mode,
        "one_way_km": round(c.one_way_km, 1),
        "days_per_week": c.days_per_week,
        "week_km": round(c.week_km),
        "week_kg": c.week_kg.rounded(),
        "year_kg": c.year_kg.rounded(0),
        "modes": [
            {
                "mode": m.mode,
                "g_per_km": m.per_km.scale(1000).rounded(0),
                "week_kg": m.week_kg.rounded(),
                "current": m.mode == c.mode,
            }
            for m in sorted(c.modes, key=lambda m: m.per_km.central)
        ],
        "vs_car_week_kg": None if c.vs_car_week_kg is None else c.vs_car_week_kg.rounded(),
        "suggestion": None
        if s is None
        else {
            "mode": s.mode,
            "days_per_week": s.days_per_week,
            "week_kg_saved": s.week_kg_saved.rounded(),
            "year_kg_saved": s.year_kg_saved.rounded(0),
            "clear": s.clear,
        },
    }


async def footprint(ctx: AppContext, user_id: UUID) -> dict[str, Any]:
    cfg = load_footprint()
    now = ctx.clock()
    async with ctx.db.session() as s:
        sched = await schedules_repo.get(s, user_id)
        meta = await routes_repo.meta(s, user_id)
        legs = await travel_repo.between(s, user_id, now - timedelta(days=RECORDED_DAYS), now)

    commute = None
    if sched is not None and meta is not None and meta[1] > 0:
        c = fp.commute(sched.commute_mode, meta[1], len(sched.office_days), cfg)
        commute = {**_commute_json(c), "route": meta[0]}

    rec = None
    if legs:
        r = fp.recorded([(leg.mode, leg.distance_m / 1000) for leg in legs], cfg)
        rec = {
            "days": RECORDED_DAYS,
            "total_kg": r.total_kg.rounded(),
            "by_mode": [
                {"mode": m, "km": round(r.km_by_mode[m], 1), "kg": r.kg_by_mode[m].rounded()}
                for m in sorted(r.km_by_mode, key=lambda m: -r.kg_by_mode[m].central)
            ],
        }

    used = {cfg.factor_source[m] for m in cfg.factor_source}
    return {
        "estimate": True,
        "unit": "kg CO2",
        "commute": commute,
        "recorded": rec,
        "sources": [
            {"title": x.title, "publisher": x.publisher, "year": x.year, "url": x.url}
            for k, x in cfg.sources.items()
            if k in used
        ],
    }
