"""OpenRouteService: the commute route between home and office, with road types.

Called once when home or office changes. Needs ORS_API_KEY; without one the route service
falls back to a straight line.
"""

from dataclasses import dataclass
from typing import Any

import httpx

from lung.domain.geo import LatLon, sample_line
from lung.integrations.http import request_json

SOURCE = "openrouteservice"

PROFILE_BY_MODE = {
    "walk": "foot-walking",
    "cycle": "cycling-regular",
    "bus": "driving-car",
    "metro": "driving-car",  # no rail routing: the road route stands in
    "two_wheeler": "driving-car",
    "car": "driving-car",
}

# ORS "waytype" extra: 0 unknown, 1 state road, 2 road, 3 street, 4 path, 5 track,
# 6 cycleway, 7 footway, 8 steps, 9 ferry, 10 construction.
WAYTYPE_CLASS = {
    1: "primary",
    2: "secondary",
    3: "residential",
    4: "path",
    5: "path",
    6: "path",
    7: "path",
    8: "path",
}
WAYCATEGORY_HIGHWAY = 1  # bit in the "waycategory" extra


@dataclass(frozen=True)
class RouteSample:
    point: LatLon
    road_class: str


@dataclass(frozen=True)
class Route:
    samples: list[RouteSample]
    distance_km: float


def _value_at(extras: dict[str, Any], name: str, vertex: int) -> int | None:
    for start, end, value in extras.get(name, {}).get("values", []):
        if start <= vertex < end or (vertex == start == end):
            return int(value)
    return None


def _road_class(extras: dict[str, Any], vertex: int) -> str:
    category = _value_at(extras, "waycategory", vertex)
    if category is not None and category & WAYCATEGORY_HIGHWAY:
        return "motorway"
    waytype = _value_at(extras, "waytype", vertex)
    return WAYTYPE_CLASS.get(waytype, "unknown") if waytype is not None else "unknown"


class OpenRouteServiceClient:
    def __init__(self, client: httpx.AsyncClient, base: str, api_key: str) -> None:
        self._client = client
        self._base = base.rstrip("/")
        self._key = api_key

    async def route(
        self, home: LatLon, office: LatLon, mode: str, every_km: float, max_points: int
    ) -> Route:
        profile = PROFILE_BY_MODE.get(mode, "driving-car")
        data = await request_json(
            self._client,
            "POST",
            f"{self._base}/v2/directions/{profile}/geojson",
            headers={"Authorization": self._key},
            json={
                "coordinates": [[home.lon, home.lat], [office.lon, office.lat]],
                "extra_info": ["waytype", "waycategory"],
            },
        )
        feature = data["features"][0]
        line = [LatLon(lat, lon) for lon, lat, *_ in feature["geometry"]["coordinates"]]
        extras = feature["properties"].get("extras", {})
        distance_km = feature["properties"]["summary"]["distance"] / 1000
        samples = [
            RouteSample(point, _road_class(extras, vertex))
            for point, vertex in sample_line(line, every_km, max_points)
        ]
        return Route(samples, distance_km)

    async def directions(
        self,
        start: LatLon,
        end: LatLon,
        profile: str,
        alternatives: int,
        every_km: float,
        max_points: int,
    ) -> list["RouteOption"]:
        return await directions(
            self._client,
            self._base,
            self._key,
            start,
            end,
            profile,
            alternatives,
            every_km,
            max_points,
        )


@dataclass(frozen=True)
class RouteOption:
    """One way from A to B, for the route planner."""

    line: list[LatLon]  # the full road geometry
    samples: list[RouteSample]  # evenly spaced points with road types, for the air
    distance_km: float
    duration_min: float


async def directions(
    client: httpx.AsyncClient,
    base: str,
    api_key: str,
    start: LatLon,
    end: LatLon,
    profile: str,
    alternatives: int,
    every_km: float,
    max_points: int,
) -> list[RouteOption]:
    """Up to `alternatives` different routes for one travel profile (driving-car,
    cycling-regular, foot-walking). ORS only offers alternatives on shorter trips."""
    body: dict[str, Any] = {
        "coordinates": [[start.lon, start.lat], [end.lon, end.lat]],
        "extra_info": ["waytype", "waycategory"],
    }
    if alternatives > 1:
        body["alternative_routes"] = {
            "target_count": alternatives,
            "share_factor": 0.6,
            "weight_factor": 1.6,
        }
    data = await request_json(
        client,
        "POST",
        f"{base.rstrip('/')}/v2/directions/{profile}/geojson",
        headers={"Authorization": api_key},
        json=body,
    )
    out: list[RouteOption] = []
    for feature in data.get("features", []):
        line = [LatLon(lat, lon) for lon, lat, *_ in feature["geometry"]["coordinates"]]
        extras = feature["properties"].get("extras", {})
        summary = feature["properties"].get("summary", {})
        samples = [
            RouteSample(point, _road_class(extras, vertex))
            for point, vertex in sample_line(line, every_km, max_points)
        ]
        out.append(
            RouteOption(
                line=line,
                samples=samples,
                distance_km=summary.get("distance", 0) / 1000,
                duration_min=summary.get("duration", 0) / 60,
            )
        )
    return out
