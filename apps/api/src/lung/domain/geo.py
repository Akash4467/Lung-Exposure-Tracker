"""Grid cells and simple geometry shared by services and integrations.

A cell is a rounded lat/lon square. Air readings are stored per cell, so everyone in the same
cell shares one fetch. 0.1° is about 11 km, close to the air model's own resolution.
"""

import math
from dataclasses import dataclass

EARTH_RADIUS_KM = 6371.0088


@dataclass(frozen=True)
class LatLon:
    lat: float
    lon: float


def cell_id(lat: float, lon: float, resolution_deg: float = 0.1) -> str:
    """'28.6_77.2': the cell's centre, rounded to the grid."""
    text = f"{resolution_deg:.10f}".rstrip("0")
    decimals = len(text.split(".")[1]) if "." in text else 0
    # "+ 0.0" turns -0.0 into 0.0 so a cell never gets two ids.
    clat = round(round(lat / resolution_deg) * resolution_deg, decimals) + 0.0
    clon = round(round(lon / resolution_deg) * resolution_deg, decimals) + 0.0
    return f"{clat:.{decimals}f}_{clon:.{decimals}f}"


def cell_center(cid: str) -> LatLon:
    lat, lon = cid.split("_")
    return LatLon(float(lat), float(lon))


def haversine_km(a: LatLon, b: LatLon) -> float:
    p1, p2 = math.radians(a.lat), math.radians(b.lat)
    dp, dl = p2 - p1, math.radians(b.lon - a.lon)
    h = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * EARTH_RADIUS_KM * math.asin(math.sqrt(h))


def midpoint(a: LatLon, b: LatLon) -> LatLon:
    return LatLon((a.lat + b.lat) / 2, (a.lon + b.lon) / 2)


def sample_line(points: list[LatLon], every_km: float, max_points: int) -> list[tuple[LatLon, int]]:
    """Evenly spaced samples along a polyline, each with the index of the vertex it follows.

    Always returns at least one sample (the middle), and at most `max_points`.
    """
    if len(points) < 2:
        return [(points[0], 0)] if points else []
    legs = [haversine_km(points[i], points[i + 1]) for i in range(len(points) - 1)]
    total = sum(legs)
    n = max(1, min(max_points, round(total / every_km)))
    # Samples sit at the centre of n equal stretches.
    targets = [(i + 0.5) * total / n for i in range(n)]

    out: list[tuple[LatLon, int]] = []
    leg, walked = 0, 0.0
    for t in targets:
        while leg < len(legs) - 1 and walked + legs[leg] < t:
            walked += legs[leg]
            leg += 1
        f = 0.0 if legs[leg] == 0 else (t - walked) / legs[leg]
        a, b = points[leg], points[leg + 1]
        out.append((LatLon(a.lat + (b.lat - a.lat) * f, a.lon + (b.lon - a.lon) * f), leg))
    return out
