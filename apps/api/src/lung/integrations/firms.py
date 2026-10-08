"""NASA FIRMS: active fire detections from satellites (VIIRS on Suomi NPP by default).

Area API: GET {base}/api/area/csv/{MAP_KEY}/{SOURCE}/{west,south,east,north}/{days}
returns CSV with latitude, longitude, acq_date (UTC), acq_time (HHMM UTC), confidence
(VIIRS: l / n / h; MODIS: 0-100), frp (fire radiative power, MW), among others.
A free MAP_KEY comes from https://firms.modaps.eosdis.nasa.gov/api/map_key/ ; without one this
client is not created and the smoke-risk flag stays "none".
"""

import csv
import io
from dataclasses import dataclass
from datetime import UTC, datetime

import httpx

from lung.domain.errors import Retryable

SOURCE = "firms"


@dataclass(frozen=True)
class FireDetection:
    lat: float
    lon: float
    detected_at: datetime  # UTC
    confidence: str  # low | nominal | high
    frp: float | None  # fire radiative power, MW


_VIIRS_CONFIDENCE = {"l": "low", "n": "nominal", "h": "high"}


def _confidence(raw: str) -> str:
    raw = raw.strip().lower()
    if raw in _VIIRS_CONFIDENCE:
        return _VIIRS_CONFIDENCE[raw]
    try:  # MODIS: a percentage
        pct = float(raw)
    except ValueError:
        return "nominal"
    return "low" if pct < 30 else "high" if pct >= 80 else "nominal"


def parse_csv(text: str) -> list[FireDetection]:
    out: list[FireDetection] = []
    for row in csv.DictReader(io.StringIO(text)):
        try:
            hhmm = row["acq_time"].zfill(4)
            when = datetime.strptime(f"{row['acq_date']} {hhmm}", "%Y-%m-%d %H%M").replace(
                tzinfo=UTC
            )
            frp = row.get("frp")
            out.append(
                FireDetection(
                    lat=float(row["latitude"]),
                    lon=float(row["longitude"]),
                    detected_at=when,
                    confidence=_confidence(row.get("confidence", "")),
                    frp=float(frp) if frp not in (None, "") else None,
                )
            )
        except (KeyError, ValueError):
            continue  # a malformed row is skipped, not fatal
    return out


class FirmsClient:
    def __init__(self, client: httpx.AsyncClient, base: str, map_key: str, source: str) -> None:
        self._client = client
        self._base = base.rstrip("/")
        self._key = map_key
        self._source = source

    async def fires(
        self, west: float, south: float, east: float, north: float, days: int
    ) -> list[FireDetection]:
        area = f"{west:.2f},{south:.2f},{east:.2f},{north:.2f}"
        url = f"{self._base}/api/area/csv/{self._key}/{self._source}/{area}/{days}"
        try:
            resp = await self._client.get(url, timeout=30.0)
        except (httpx.TimeoutException, httpx.TransportError) as e:
            raise Retryable(f"FIRMS: {type(e).__name__}") from e
        if resp.status_code in (429, 500, 502, 503, 504):
            raise Retryable(f"FIRMS: HTTP {resp.status_code}")
        resp.raise_for_status()
        text = resp.text
        if not text.lstrip().lower().startswith("latitude"):
            # FIRMS answers some errors (bad key, quota) with a plain-text 200
            raise Retryable(f"FIRMS: unexpected reply {text[:80]!r}")
        return parse_csv(text)
