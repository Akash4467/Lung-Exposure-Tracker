"""Provider clients against canned responses (httpx.MockTransport): no network, no keys."""

from datetime import UTC, datetime
from typing import Any

import httpx
import pytest

from lung.domain.errors import Retryable
from lung.domain.geo import LatLon
from lung.integrations.open_meteo import OpenMeteoClient
from lung.integrations.openrouteservice import OpenRouteServiceClient

AIR = {
    "hourly": {
        "time": ["2026-10-04T00:00", "2026-10-04T01:00", "2026-10-04T02:00"],
        "pm2_5": [120.5, 130.0, None],
        "pm10": [200.0, 210.0, None],
    }
}
WEATHER = {
    "hourly": {
        "time": ["2026-10-04T00:00", "2026-10-04T01:00", "2026-10-04T02:00"],
        "wind_speed_10m": [2.1, 2.5, 3.0],
        "wind_direction_10m": [300, 310, 320],
    }
}


def _client(handler: Any) -> httpx.AsyncClient:
    return httpx.AsyncClient(transport=httpx.MockTransport(handler))


async def test_open_meteo_parses_and_joins_air_and_wind() -> None:
    seen: list[httpx.Request] = []

    def handler(req: httpx.Request) -> httpx.Response:
        seen.append(req)
        return httpx.Response(200, json=AIR if "air-quality" in req.url.path else WEATHER)

    async with _client(handler) as http:
        om = OpenMeteoClient(http, "https://air.test/v1", "https://wx.test/v1", 1, 2)
        rows = await om.hourly(28.6, 77.2)

    assert [r.hour for r in rows] == [
        datetime(2026, 10, 4, 0, tzinfo=UTC),
        datetime(2026, 10, 4, 1, tzinfo=UTC),
    ]  # the blank third hour is dropped
    assert (rows[0].pm25, rows[0].pm10, rows[0].wind_speed, rows[0].wind_dir) == (
        120.5,
        200.0,
        2.1,
        300,
    )
    air_req = next(r for r in seen if "air-quality" in r.url.path)
    assert air_req.url.params["timezone"] == "GMT"
    assert air_req.url.params["hourly"] == "pm2_5,pm10"


@pytest.mark.parametrize("status", [429, 500, 503])
async def test_open_meteo_temporary_errors_are_retryable(status: int) -> None:
    async with _client(lambda req: httpx.Response(status)) as http:
        om = OpenMeteoClient(http, "https://air.test/v1", "https://wx.test/v1", 1, 2)
        with pytest.raises(Retryable):
            await om.hourly(28.6, 77.2)


async def test_open_meteo_timeout_is_retryable() -> None:
    def handler(req: httpx.Request) -> httpx.Response:
        raise httpx.ReadTimeout("slow", request=req)

    async with _client(handler) as http:
        om = OpenMeteoClient(http, "https://air.test/v1", "https://wx.test/v1", 1, 2)
        with pytest.raises(Retryable):
            await om.hourly(28.6, 77.2)


def _ors_response() -> dict[str, Any]:
    # 4 vertices west→east; vertex 0-1 highway, 1-2 state road, 2-3 street
    return {
        "features": [
            {
                "geometry": {
                    "coordinates": [[77.20, 28.6], [77.25, 28.6], [77.30, 28.6], [77.35, 28.6]]
                },
                "properties": {
                    "summary": {"distance": 14600.0},
                    "extras": {
                        "waycategory": {"values": [[0, 1, 1], [1, 3, 0]]},
                        "waytype": {"values": [[0, 1, 1], [1, 2, 1], [2, 3, 3]]},
                    },
                },
            }
        ]
    }


async def test_ors_route_samples_with_road_classes() -> None:
    seen: list[httpx.Request] = []

    def handler(req: httpx.Request) -> httpx.Response:
        seen.append(req)
        return httpx.Response(200, json=_ors_response())

    async with _client(handler) as http:
        ors = OpenRouteServiceClient(http, "https://ors.test", "secret-key")
        route = await ors.route(LatLon(28.6, 77.2), LatLon(28.6, 77.35), "two_wheeler", 5.0, 20)

    assert route.distance_km == pytest.approx(14.6)
    assert [s.road_class for s in route.samples] == ["motorway", "primary", "residential"]
    assert seen[0].url.path == "/v2/directions/driving-car/geojson"
    assert seen[0].headers["Authorization"] == "secret-key"


async def test_ors_bad_key_raises_http_error_not_retryable() -> None:
    async with _client(lambda req: httpx.Response(403, json={"error": "key"})) as http:
        ors = OpenRouteServiceClient(http, "https://ors.test", "bad")
        with pytest.raises(httpx.HTTPStatusError):
            await ors.route(LatLon(28.6, 77.2), LatLon(28.6, 77.35), "walk", 1.0, 20)
