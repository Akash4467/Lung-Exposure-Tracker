"""Place search and reverse lookup over OpenStreetMap data.

Primary: Nominatim (fast, finds localities like housing societies). Its usage policy allows
at most 1 request per second with an identifying User-Agent, so callers go through
`services/geo_service.py`, which caches results and spaces requests out.
Fallback: Photon (komoot), slower but no rate limit for light use.
For real scale, self-host Photon or Nominatim (see docs/deployment.md).
"""

from dataclasses import dataclass
from typing import Any

import httpx

from lung.integrations.http import request_json

USER_AGENT = "LungExposureTracker/0.1 (air exposure app; contact via app store listing)"


@dataclass(frozen=True)
class GeoPlace:
    label: str
    detail: str
    lat: float
    lon: float


def _join(parts: list[str | None], skip: str) -> str:
    seen: list[str] = []
    for p in parts:
        if p and p != skip and p not in seen:
            seen.append(p)
    return ", ".join(seen)


def _from_nominatim(item: dict[str, Any]) -> GeoPlace:
    a = item.get("address") or {}
    label = (
        item.get("name")
        or a.get("road")
        or a.get("suburb")
        or (item.get("display_name") or "").split(",")[0]
        or "Unnamed place"
    )
    city = a.get("city") or a.get("town") or a.get("village") or a.get("county")
    country = a.get("country") if a.get("country_code") != "in" else None
    detail = _join([a.get("road"), a.get("suburb"), city, a.get("state"), country], label)
    return GeoPlace(label, detail, float(item["lat"]), float(item["lon"]))


def _from_photon(f: dict[str, Any]) -> GeoPlace:
    p = f.get("properties", {})
    street = " ".join(x for x in (p.get("housenumber"), p.get("street")) if x)
    label = p.get("name") or street or p.get("district") or p.get("city") or "Unnamed place"
    country = p.get("country") if p.get("countrycode") != "IN" else None
    detail = _join([street, p.get("district"), p.get("city"), p.get("state"), country], label)
    lon, lat = f["geometry"]["coordinates"][:2]
    return GeoPlace(label, detail, float(lat), float(lon))


class Geocoder:
    def __init__(self, client: httpx.AsyncClient, nominatim: str, photon: str) -> None:
        self._client = client
        self._nominatim = nominatim.rstrip("/")
        self._photon = photon.rstrip("/")

    async def nominatim_search(
        self, q: str, near: tuple[float, float] | None, limit: int
    ) -> list[GeoPlace]:
        params: dict[str, Any] = {
            "q": q,
            "format": "jsonv2",
            "addressdetails": 1,
            "limit": limit,
            "accept-language": "en",
        }
        if near:  # prefer results around the person, without excluding the rest
            lat, lon = near
            params["viewbox"] = f"{lon - 1},{lat + 1},{lon + 1},{lat - 1}"
            params["bounded"] = 0
        data = await request_json(
            self._client,
            "GET",
            f"{self._nominatim}/search",
            params=params,
            headers={"User-Agent": USER_AGENT},
            timeout=6.0,
        )
        return [_from_nominatim(x) for x in data]

    async def nominatim_reverse(self, lat: float, lon: float) -> GeoPlace | None:
        data = await request_json(
            self._client,
            "GET",
            f"{self._nominatim}/reverse",
            params={
                "lat": lat,
                "lon": lon,
                "format": "jsonv2",
                "addressdetails": 1,
                "zoom": 17,
                "accept-language": "en",
            },
            headers={"User-Agent": USER_AGENT},
            timeout=6.0,
        )
        if not data or "lat" not in data:
            return None
        place = _from_nominatim(data)
        return GeoPlace(place.label, place.detail, lat, lon)

    async def photon_search(
        self, q: str, near: tuple[float, float] | None, limit: int
    ) -> list[GeoPlace]:
        params: dict[str, Any] = {"q": q, "limit": limit, "lang": "en"}
        if near:
            params.update({"lat": near[0], "lon": near[1], "location_bias_scale": 0.3})
        data = await request_json(
            self._client, "GET", f"{self._photon}/api/", params=params, timeout=8.0
        )
        return [_from_photon(f) for f in data.get("features", [])]
