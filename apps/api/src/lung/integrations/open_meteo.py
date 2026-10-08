"""Open-Meteo: hourly PM2.5/PM10 (air-quality API) and wind (weather API) for one point;
the current PM2.5 for many points at once (the map); a multi-day forecast for any place.

No key needed. Times are requested in GMT so every hour comes back in UTC.
"""

import asyncio
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any

import httpx

from lung.domain.air import HourlyAir
from lung.integrations.http import request_json

SOURCE = "open_meteo"


def _series(payload: dict[str, Any], key: str) -> dict[datetime, float | None]:
    hourly = payload.get("hourly", {})
    times = hourly.get("time", [])
    values = hourly.get(key, [])
    return {
        datetime.fromisoformat(t).replace(tzinfo=UTC): v
        for t, v in zip(times, values, strict=False)
    }


@dataclass(frozen=True)
class PlaceForecast:
    lat: float
    lon: float
    utc_offset_s: int  # the place's own time zone (for grouping hours into local days)
    hours: list[tuple[datetime, float, float | None]]  # (UTC hour, pm2.5, pm10)


MAX_POINTS_PER_CALL = 50


class OpenMeteoClient:
    def __init__(
        self,
        client: httpx.AsyncClient,
        air_base: str,
        weather_base: str,
        past_days: int,
        forecast_days: int,
    ) -> None:
        self._client = client
        self._air = air_base.rstrip("/")
        self._weather = weather_base.rstrip("/")
        self._common = {
            "timezone": "GMT",
            "past_days": past_days,
            "forecast_days": forecast_days,
        }

    async def hourly(self, lat: float, lon: float) -> list[HourlyAir]:
        point = {"latitude": f"{lat:.4f}", "longitude": f"{lon:.4f}"}
        air, weather = await asyncio.gather(
            request_json(
                self._client,
                "GET",
                f"{self._air}/air-quality",
                params={**point, **self._common, "hourly": "pm2_5,pm10"},
            ),
            request_json(
                self._client,
                "GET",
                f"{self._weather}/forecast",
                params={
                    **point,
                    **self._common,
                    "hourly": "wind_speed_10m,wind_direction_10m",
                    "wind_speed_unit": "ms",
                },
            ),
        )
        pm25 = _series(air, "pm2_5")
        pm10 = _series(air, "pm10")
        speed = _series(weather, "wind_speed_10m")
        direction = _series(weather, "wind_direction_10m")
        return [
            HourlyAir(hour, value, pm10.get(hour), speed.get(hour), direction.get(hour))
            for hour, value in sorted(pm25.items())
            if value is not None  # the model leaves the far end of the forecast blank
        ]

    async def current_many(self, points: list[tuple[float, float]]) -> list[float | None]:
        """PM2.5 right now at each (lat, lon), in the same order. Batched; one call per 50."""
        out: list[float | None] = []
        for i in range(0, len(points), MAX_POINTS_PER_CALL):
            chunk = points[i : i + MAX_POINTS_PER_CALL]
            payload = await request_json(
                self._client,
                "GET",
                f"{self._air}/air-quality",
                params={
                    "latitude": ",".join(f"{lat:.3f}" for lat, _ in chunk),
                    "longitude": ",".join(f"{lon:.3f}" for _, lon in chunk),
                    "current": "pm2_5",
                    "timezone": "GMT",
                },
            )
            items = payload if isinstance(payload, list) else [payload]
            out.extend((it.get("current") or {}).get("pm2_5") for it in items)
        return out

    async def place_forecast(self, lat: float, lon: float, days: int) -> PlaceForecast:
        """Hourly PM2.5/PM10 for any place: yesterday plus `days` ahead, in UTC, with the
        place's own UTC offset (asked for with timezone=auto)."""
        payload = await request_json(
            self._client,
            "GET",
            f"{self._air}/air-quality",
            params={
                "latitude": f"{lat:.4f}",
                "longitude": f"{lon:.4f}",
                "hourly": "pm2_5,pm10",
                "timezone": "auto",
                "past_days": 1,
                "forecast_days": days,
            },
        )
        offset = int(payload.get("utc_offset_seconds", 0))
        hourly = payload.get("hourly", {})
        hours: list[tuple[datetime, float, float | None]] = []
        for t, p25, p10 in zip(
            hourly.get("time", []),
            hourly.get("pm2_5", []),
            hourly.get("pm10", []),
            strict=False,
        ):
            if p25 is None:
                continue
            local = datetime.fromisoformat(t)
            hours.append(((local - timedelta(seconds=offset)).replace(tzinfo=UTC), p25, p10))
        return PlaceForecast(lat, lon, offset, hours)
