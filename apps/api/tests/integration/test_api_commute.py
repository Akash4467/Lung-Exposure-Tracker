"""The commute on the map: route points with roadside PM2.5, and every way of travelling."""

import httpx
import pytest

from lung.services.context import AppContext

from .test_api_app import _onboarded, _session

pytestmark = pytest.mark.integration


async def test_commute_view(client: httpx.AsyncClient, ctx: AppContext) -> None:
    h = await _onboarded(client, ctx)
    r = await client.get("/v1/me/commute", headers=h)
    assert r.status_code == 200, r.text
    c = r.json()
    assert c["mode"] == "bus_metro" and c["distance_km"] > 0
    am, pm = c["morning"], c["evening"]
    assert len(am["points"]) >= 3
    # evening runs office -> home
    assert am["points"][0]["lat"] == pm["points"][-1]["lat"]
    # 08:30 IST is a 200 µg/m³ rush hour in the fake; roadside = area x the road's factor
    factors = ctx.cfg.road_factor
    for p in am["points"]:
        assert p["pm25"] == pytest.approx(200 * factors.get(p["road_class"], 1.0))
    assert am["avg_pm25"] >= 200

    modes = {m["mode"]: m for m in c["modes"]}
    assert set(modes) == {"walk", "cycle", "bus_metro", "two_wheeler", "car"}
    assert modes["bus_metro"]["current"] and not modes["car"]["current"]
    # a car keeps some of it out and you sit still: the least per hour; cycling the most
    assert c["modes"][0]["mode"] == "car"
    assert c["modes"][-1]["mode"] == "cycle"
    assert modes["car"]["inside_pm25"] == pytest.approx(am["avg_pm25"] * 0.6, rel=0.01)


async def test_commute_needs_onboarding(client: httpx.AsyncClient) -> None:
    h = await _session(client)
    r = await client.get("/v1/me/commute", headers=h)
    assert r.status_code == 404 and r.json()["error"]["code"] == "profile_incomplete"
