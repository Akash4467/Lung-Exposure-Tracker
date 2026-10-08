"""Plan a trip from A to B like a maps app, but by the air: each route coloured by roadside
PM2.5 right now, the cleanest drive among the alternatives, and what each way of travelling
would put in your lungs for the whole trip.

    trip dose (µg) = average roadside PM2.5 × share reaching you (vehicle) × your breathing
                     rate for that way of travelling (m³/h) × trip hours

Air: Open-Meteo's current PM2.5 on the map's 0.1° lattice (shared cache with the map), ×
the road-type factor at each sampled point. Routes: OpenRouteService (driving with up to 3
alternatives, cycling, walking); without a key, straight lines at typical speeds.
"""

import asyncio
from typing import Any
from uuid import UUID

import httpx
import structlog

from lung.domain.errors import InvalidInput, NotFound, Retryable
from lung.domain.geo import LatLon, haversine_km, sample_line
from lung.engine.dose import breathing_rate
from lung.engine.models import Profile
from lung.integrations.openrouteservice import RouteOption, RouteSample
from lung.repositories import profiles as profiles_repo
from lung.services.context import AppContext
from lung.services.map_service import GRID_TTL_S, _fetch_lock, _grid_key

EVERY_KM = 1.0
MAX_SAMPLES = 40
MAX_PATH = 200
MAX_TRIP_KM = 800
MAX_WALK_KM = 25
MAX_CYCLE_KM = 60
ALTERNATIVES_UNDER_KM = 80  # ORS offers alternative routes only on shorter trips
STRAIGHT_SPEED_KMH = {"driving-car": 28, "cycling-regular": 14, "foot-walking": 4.8}
DETOUR = 1.3  # straight-line fallback: roads are ~30 % longer than the crow flies
BUS_SLOWER = 1.3  # buses stop; same roads as the drive, ~30 % longer
METRO_SLOWER = 1.0  # rough: faster than traffic, plus the walk to and from stations

log = structlog.get_logger()


def _snap(v: float) -> float:
    return round(round(v / 0.1) * 0.1, 4)


async def _pm25_at(ctx: AppContext, points: list[LatLon]) -> dict[tuple[float, float], float]:
    """Current PM2.5 at each point's 0.1° lattice node, shared with the map's grid cache."""
    nodes = sorted({(_snap(p.lat), _snap(p.lon)) for p in points})
    keys = [_grid_key(0.1, lat, lon) for lat, lon in nodes]
    cached = await asyncio.gather(*(ctx.cache.get_json(k) for k in keys))
    values: dict[tuple[float, float], float] = {}
    missing: list[int] = []
    for i, c in enumerate(cached):
        if c is not None and c.get("pm25") is not None:
            values[nodes[i]] = c["pm25"]
        elif c is None:
            missing.append(i)
    if missing:
        async with _fetch_lock:
            fresh = await ctx.air.current_many([nodes[i] for i in missing])
        for i, v in zip(missing, fresh, strict=False):
            await ctx.cache.set_json(keys[i], {"pm25": v}, GRID_TTL_S)
            if v is not None:
                values[nodes[i]] = v
    return values


def _straight(start: LatLon, end: LatLon, profile: str) -> RouteOption:
    km = haversine_km(start, end) * DETOUR
    line = [start, end]
    samples = [RouteSample(p, "unknown") for p, _ in sample_line(line, EVERY_KM, MAX_SAMPLES)]
    return RouteOption(line, samples, km, km / STRAIGHT_SPEED_KMH[profile] * 60)


async def _routes(
    ctx: AppContext, start: LatLon, end: LatLon, profile: str, alts: int
) -> tuple[list[RouteOption], bool]:
    """Real road routes, or a straight line if the provider is missing, down or finds none
    (e.g. no road between the points)."""
    if ctx.routes is not None:
        try:
            got = await ctx.routes.directions(start, end, profile, alts, EVERY_KM, MAX_SAMPLES)
            if got:
                return got, True
        except (Retryable, httpx.HTTPError) as e:
            log.warning("route_planner_fallback", profile=profile, error=str(e))
    return [_straight(start, end, profile)], False


def _path(option: RouteOption, roadside: list[float | None]) -> list[list[float | None]]:
    """The road geometry (≤ MAX_PATH vertices) with the roadside PM2.5 of the nearest sample."""
    line = option.line
    if len(line) > MAX_PATH:
        step = (len(line) - 1) / (MAX_PATH - 1)
        idx = [round(i * step) for i in range(MAX_PATH)]
    else:
        idx = list(range(len(line)))
    n = max(len(roadside), 1)
    out: list[list[float | None]] = []
    for i in idx:
        s = min(n - 1, int(i / max(len(line) - 1, 1) * n)) if roadside else 0
        pm = roadside[s] if roadside else None
        out.append([round(line[i].lat, 5), round(line[i].lon, 5), pm])
    return out


async def plan(ctx: AppContext, user_id: UUID, start: LatLon, end: LatLon) -> dict[str, Any]:
    straight = haversine_km(start, end)
    if straight < 0.2:
        raise InvalidInput("start and destination are the same place", "same_place")
    if straight > MAX_TRIP_KM:
        raise InvalidInput(f"routes are planned up to {MAX_TRIP_KM} km", "too_far")
    async with ctx.db.session() as s:
        row = await profiles_repo.get(s, user_id)
    if row is None:
        raise NotFound("finish onboarding first", "profile_incomplete")
    profile = Profile(row.age, row.sex, row.sensitive, row.weight_kg)  # type: ignore[arg-type]
    cfg = ctx.cfg

    wanted = [("driving-car", 3 if straight < ALTERNATIVES_UNDER_KM else 1)]
    if straight <= MAX_CYCLE_KM:
        wanted.append(("cycling-regular", 1))
    if straight <= MAX_WALK_KM:
        wanted.append(("foot-walking", 1))
    found = await asyncio.gather(*(_routes(ctx, start, end, p, a) for p, a in wanted))

    by_profile: dict[str, list[RouteOption]] = {}
    real = True
    for (p, _), (opts, ok) in zip(wanted, found, strict=True):
        by_profile[p] = opts
        real = real and ok
    points = [x.point for opts in by_profile.values() for r in opts for x in r.samples]
    air = await _pm25_at(ctx, points)

    options: list[dict[str, Any]] = []
    for p, opts in by_profile.items():
        for n, r in enumerate(opts):
            roadside: list[float | None] = []
            for x in r.samples:
                v = air.get((_snap(x.point.lat), _snap(x.point.lon)))
                road = cfg.road_factor.get(x.road_class, cfg.road_factor["unknown"])
                roadside.append(round(v * road, 1) if v is not None else None)
            known = [v for v in roadside if v is not None]
            options.append(
                {
                    "id": f"{p}:{n}",
                    "profile": p,
                    "distance_km": round(r.distance_km, 1),
                    "duration_min": round(r.duration_min),
                    "avg_pm25": round(sum(known) / len(known), 1) if known else None,
                    "path": _path(r, roadside),
                }
            )

    drives = [o for o in options if o["profile"] == "driving-car"]
    fastest = min(drives, key=lambda o: o["duration_min"]) if drives else None
    with_air = [o for o in drives if o["avg_pm25"] is not None]
    cleanest = min(with_air, key=lambda o: o["avg_pm25"]) if with_air else None
    for o in options:
        o["fastest"] = o is fastest
        o["cleanest"] = o is cleanest and len(drives) > 1
    cleaner_by = (
        round(100 * (1 - cleanest["avg_pm25"] / fastest["avg_pm25"]), 1)
        if cleanest and fastest and fastest["avg_pm25"] and cleanest is not fastest
        else 0.0
    )

    modes: list[dict[str, Any]] = []

    def add(mode: str, option: dict[str, Any] | None, slower: float = 1.0) -> None:
        if option is None or option["avg_pm25"] is None:
            return
        activity = mode if mode in ("walk", "cycle") else cfg.commute_activity[mode]  # type: ignore[index]
        factor = 1.0 if mode in ("walk", "cycle") else cfg.commute_factor[mode]  # type: ignore[index]
        rate = breathing_rate(profile, activity, cfg)  # type: ignore[arg-type]
        minutes = option["duration_min"] * slower
        inside = option["avg_pm25"] * factor
        modes.append(
            {
                "mode": mode,
                "option_id": option["id"],
                "duration_min": round(minutes),
                "inside_pm25": round(inside, 1),
                "dose_ug": round(inside * rate * minutes / 60, 1),
            }
        )

    drive = cleanest or fastest
    add("car", drive)
    add("two_wheeler", drive)
    add("bus", drive, BUS_SLOWER)
    add("metro", drive, METRO_SLOWER)
    add("cycle", next((o for o in options if o["profile"] == "cycling-regular"), None))
    add("walk", next((o for o in options if o["profile"] == "foot-walking"), None))
    modes.sort(key=lambda m: m["dose_ug"])

    return {
        "from": {"lat": start.lat, "lon": start.lon},
        "to": {"lat": end.lat, "lon": end.lon},
        "options": options,
        "modes": modes,
        "cleaner_by_pct": cleaner_by,
        "routes_from": "openrouteservice" if real else "straight_line",
        "estimated": True,
    }
