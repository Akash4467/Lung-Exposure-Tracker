"""Opt-in route recording: GPS points from the phone become travel legs.

How a leg's way of travelling is decided, per stretch between two GPS points:
1. the phone's own activity reading (Android activity recognition) when it is at least of
   medium confidence: walking, running, cycling, in a vehicle, still;
2. otherwise the speed: < 0.6 m/s still (not travel), < 2.5 walking (9 km/h), < 4.5 running
   (16 km/h), < 8.5 cycling if the person cycles to work, else a vehicle; faster is a vehicle.
A vehicle is the person's declared vehicle (bus/metro, two-wheeler or car), or bus/metro if
they declared walking or cycling.

Consecutive stretches with the same way of travelling in the same grid cell form a leg.
Gaps over 10 minutes split legs; legs under 2 minutes are dropped as noise. Raw points are
not kept: each leg stores a simplified line (≤ 30 points, ~100 m precision) for the map.
"""

from dataclasses import dataclass
from datetime import date, datetime, time, timedelta
from itertools import pairwise
from typing import Any
from uuid import UUID
from zoneinfo import ZoneInfo

from lung.domain.errors import InvalidInput, NotFound
from lung.domain.geo import LatLon, cell_id, haversine_km
from lung.repositories import profiles as profiles_repo
from lung.repositories import schedules as schedules_repo
from lung.repositories import travel as travel_repo
from lung.repositories.travel import LegRow
from lung.services import ingest_service
from lung.services.context import AppContext

MAX_POINTS = 2000
MAX_AGE = timedelta(hours=48)
MAX_ACCURACY_M = 100
MAX_GAP = timedelta(minutes=10)
MIN_LEG = timedelta(minutes=2)
MAX_PATH_POINTS = 30
VEHICLES = ("bus_metro", "two_wheeler", "car")
ACTIVITY_TO_MODE = {"walking": "walk", "running": "run", "cycling": "cycle"}


@dataclass(frozen=True)
class GpsPoint:
    t: datetime
    lat: float
    lon: float
    speed: float | None = None  # m/s, from the phone
    accuracy: float | None = None  # metres
    activity: str | None = None  # walking | running | cycling | automotive | stationary
    confident: bool = False  # the activity reading is at least medium confidence


def vehicle_for(declared: str) -> str:
    return declared if declared in VEHICLES else "bus_metro"


def classify(speed: float, activity: str | None, confident: bool, declared: str) -> str | None:
    """The way of travelling for one stretch, or None when the person was still."""
    if activity and confident:
        if activity == "stationary":
            return None
        if activity == "automotive":
            return vehicle_for(declared)
        if activity in ACTIVITY_TO_MODE:
            return ACTIVITY_TO_MODE[activity]
    if speed < 0.6:
        return None
    if speed < 2.5:
        return "walk"
    if speed < 4.5:
        return "run"
    if speed < 8.5:
        return "cycle" if declared == "cycle" else vehicle_for(declared)
    return vehicle_for(declared)


def _simplify(path: list[list[float]]) -> list[list[float]]:
    if len(path) > MAX_PATH_POINTS:
        step = (len(path) - 1) / (MAX_PATH_POINTS - 1)
        path = [path[round(i * step)] for i in range(MAX_PATH_POINTS)]
    return [[round(lat, 3), round(lon, 3)] for lat, lon in path]


def build_legs(points: list[GpsPoint], declared: str, resolution_deg: float) -> list[LegRow]:
    pts = sorted(
        (p for p in points if p.accuracy is None or p.accuracy <= MAX_ACCURACY_M),
        key=lambda p: p.t,
    )
    legs: list[LegRow] = []
    cur: dict[str, Any] | None = None

    def close() -> None:
        nonlocal cur
        if cur and cur["end"] - cur["start"] >= MIN_LEG:
            legs.append(
                LegRow(
                    start_at=cur["start"],
                    end_at=cur["end"],
                    mode=cur["mode"],
                    cell_id=cur["cell"],
                    distance_m=round(cur["dist"]),
                    path=_simplify(cur["path"]),
                    source="gps+activity" if cur["hinted"] else "gps",
                )
            )
        cur = None

    for a, b in pairwise(pts):
        dt = (b.t - a.t).total_seconds()
        if dt <= 0 or b.t - a.t > MAX_GAP:
            close()
            continue
        metres = haversine_km(LatLon(a.lat, a.lon), LatLon(b.lat, b.lon)) * 1000
        speed = b.speed if b.speed is not None and b.speed >= 0 else metres / dt
        mode = classify(speed, b.activity, b.confident, declared)
        if mode is None:
            close()
            continue
        cell = cell_id(a.lat, a.lon, resolution_deg)
        if cur and cur["mode"] == mode and cur["cell"] == cell and cur["end"] == a.t:
            cur["end"] = b.t
            cur["dist"] += metres
            cur["path"].append([b.lat, b.lon])
            cur["hinted"] = cur["hinted"] or (b.activity is not None and b.confident)
        else:
            close()
            cur = {
                "start": a.t,
                "end": b.t,
                "mode": mode,
                "cell": cell,
                "dist": metres,
                "path": [[a.lat, a.lon], [b.lat, b.lon]],
                "hinted": b.activity is not None and b.confident,
            }
    close()
    return legs


async def add_points(ctx: AppContext, user_id: UUID, points: list[GpsPoint]) -> dict[str, Any]:
    if len(points) > MAX_POINTS:
        raise InvalidInput(f"at most {MAX_POINTS} points per call", "too_many_points")
    now = ctx.clock()
    for p in points:
        if p.t < now - MAX_AGE or p.t > now + timedelta(minutes=5):
            raise InvalidInput("points must be from the last 48 hours", "bad_point")
    async with ctx.db.session() as s:
        sched = await schedules_repo.get(s, user_id)
        declared = sched.commute_mode if sched else "bus_metro"
        legs = build_legs(points, declared, ctx.settings.cell_resolution_deg)
        await travel_repo.add_many(s, user_id, legs)
    if legs:
        for c in {leg.cell_id for leg in legs}:
            await ctx.queue.send(ctx.settings.sqs_ingest_url, ingest_service.fetch_msg(c))
        await ingest_service.queue_recompute(ctx, user_id)
    return {"points": len(points), "legs": len(legs)}


def leg_json(leg: LegRow) -> dict[str, Any]:
    return {
        "id": leg.id,
        "start": leg.start_at.isoformat(),
        "end": leg.end_at.isoformat(),
        "mode": leg.mode,
        "distance_m": leg.distance_m,
        "path": leg.path,
        "source": leg.source,
    }


async def legs_between(
    ctx: AppContext, user_id: UUID, start: datetime, end: datetime
) -> list[dict[str, Any]]:
    async with ctx.db.session() as s:
        return [leg_json(x) for x in await travel_repo.between(s, user_id, start, end)]


async def delete_all(ctx: AppContext, user_id: UUID) -> int:
    async with ctx.db.session() as s:
        n = await travel_repo.delete_all(s, user_id)
    await ingest_service.queue_recompute(ctx, user_id)
    return n


async def legs_for_day(ctx: AppContext, user_id: UUID, day: date | None) -> dict[str, Any]:
    async with ctx.db.session() as s:
        profile = await profiles_repo.get(s, user_id)
        if profile is None:
            raise NotFound("finish onboarding first", "profile_incomplete")
        tz = ZoneInfo(profile.timezone)
        day = day or ctx.clock().astimezone(tz).date()
        start = datetime.combine(day, time(0), tzinfo=tz)
        legs = await travel_repo.between(s, user_id, start, start + timedelta(days=1))
    return {"date": day.isoformat(), "legs": [leg_json(x) for x in legs]}
