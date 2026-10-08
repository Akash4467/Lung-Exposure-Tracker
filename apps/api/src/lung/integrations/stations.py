"""Ground monitoring stations, used to correct the gridded model near them.

Two sources, both official monitors only (no low-cost sensors):
- OpenAQ v3 (worldwide; X-API-Key). Locations with a PM2.5 sensor near a point, keeping
  `isMonitor` ones that reported recently, then each one's latest PM2.5.
  Note: OpenAQ's India government feeds were mostly stale in Oct 2026, so in India this
  often finds nothing; it works where feeds are live (and will when they resume).
- CPCB real-time data on data.gov.in (India; api-key). One list of every station's latest
  pollutant values (min / max / avg, timestamped in IST), filtered to PM2.5. Fetched once
  and shared across cells.
"""

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any
from zoneinfo import ZoneInfo

import httpx

from lung.integrations.http import request_json

IST = ZoneInfo("Asia/Kolkata")


@dataclass(frozen=True)
class StationReading:
    lat: float
    lon: float
    pm25: float
    at: datetime  # UTC
    provider: str  # "openaq:<provider>" or "cpcb"
    name: str


class OpenAQClient:
    def __init__(self, client: httpx.AsyncClient, base: str, api_key: str) -> None:
        self._client = client
        self._base = base.rstrip("/")
        self._headers = {"X-API-Key": api_key}

    async def _get(self, path: str, **params: Any) -> Any:
        return await request_json(
            self._client,
            "GET",
            f"{self._base}{path}",
            params=params,
            headers=self._headers,
            timeout=20.0,
        )

    async def near(
        self, lat: float, lon: float, radius_km: float, max_age: timedelta, now: datetime
    ) -> list[StationReading]:
        data = await self._get(
            "/v3/locations",
            coordinates=f"{lat:.4f},{lon:.4f}",
            radius=int(min(radius_km, 25) * 1000),  # OpenAQ caps the radius at 25 km
            parameters_id=2,  # PM2.5
            limit=100,
        )
        out: list[StationReading] = []
        for loc in data.get("results", []):
            if not loc.get("isMonitor") or loc.get("isMobile"):
                continue  # official, fixed monitors only
            last = (loc.get("datetimeLast") or {}).get("utc")
            if not last or now - _utc(last) > max_age:
                continue
            pm_sensor = next(
                (s["id"] for s in loc.get("sensors", []) if s["parameter"]["name"] == "pm25"),
                None,
            )
            if pm_sensor is None:
                continue
            latest = await self._get(f"/v3/locations/{loc['id']}/latest")
            for r in latest.get("results", []):
                if r.get("sensorsId") != pm_sensor or r.get("value") is None:
                    continue
                at = _utc(r["datetime"]["utc"])
                if now - at > max_age or r["value"] < 0:
                    continue
                c = loc.get("coordinates") or r.get("coordinates") or {}
                out.append(
                    StationReading(
                        lat=float(c["latitude"]),
                        lon=float(c["longitude"]),
                        pm25=float(r["value"]),
                        at=at,
                        provider=f"openaq:{(loc.get('provider') or {}).get('name', '?')}",
                        name=loc.get("name") or str(loc["id"]),
                    )
                )
        return out


def _utc(iso: str) -> datetime:
    return datetime.fromisoformat(iso.replace("Z", "+00:00")).astimezone(UTC)


CPCB_RESOURCE = "3b01bcb8-0b14-4abf-b6f2-c1bfd384ba69"  # "Real time Air Quality Index"


def parse_cpcb(records: list[dict[str, Any]]) -> list[StationReading]:
    """data.gov.in rows → PM2.5 readings. `avg_value` is the station's current average used
    for its AQI; `last_update` is "dd-mm-yyyy HH:MM:SS" in IST."""
    out: list[StationReading] = []
    for r in records:
        if str(r.get("pollutant_id", "")).upper() != "PM2.5":
            continue
        try:
            value = float(r["avg_value"])
            at = datetime.strptime(r["last_update"], "%d-%m-%Y %H:%M:%S").replace(tzinfo=IST)
            out.append(
                StationReading(
                    lat=float(r["latitude"]),
                    lon=float(r["longitude"]),
                    pm25=value,
                    at=at.astimezone(UTC),
                    provider="cpcb",
                    name=f"{r.get('station', '?')}",
                )
            )
        except (KeyError, ValueError, TypeError):
            continue  # "NA" values and malformed rows
    return out


class CpcbClient:
    def __init__(self, client: httpx.AsyncClient, base: str, api_key: str) -> None:
        self._client = client
        self._base = base.rstrip("/")
        self._key = api_key

    async def all_pm25(self) -> list[StationReading]:
        rows: list[dict[str, Any]] = []
        offset = 0
        while offset < 5000:
            data = await request_json(
                self._client,
                "GET",
                f"{self._base}/resource/{CPCB_RESOURCE}",
                params={
                    "api-key": self._key,
                    "format": "json",
                    "limit": 1000,
                    "offset": offset,
                    "filters[pollutant_id]": "PM2.5",
                },
                timeout=40.0,
            )
            page = data.get("records", [])
            rows.extend(page)
            if len(page) < 1000:
                break
            offset += 1000
        return parse_cpcb(rows)
