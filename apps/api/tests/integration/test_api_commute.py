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
    assert c["mode"] == "metro" and c["distance_km"] > 0
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
    assert set(modes) == {"walk", "cycle", "bus", "metro", "two_wheeler", "car"}
    assert modes["metro"]["current"] and not modes["car"]["current"]
    # a car keeps some of it out and you sit still: the least per hour; cycling the most
    assert c["modes"][0]["mode"] == "car"
    assert c["modes"][-1]["mode"] == "cycle"
    assert modes["car"]["inside_pm25"] == pytest.approx(am["avg_pm25"] * 0.6, rel=0.01)


async def test_commute_needs_onboarding(client: httpx.AsyncClient) -> None:
    h = await _session(client)
    r = await client.get("/v1/me/commute", headers=h)
    assert r.status_code == 404 and r.json()["error"]["code"] == "profile_incomplete"


async def test_footprint_for_a_metro_commuter(client: httpx.AsyncClient, ctx: AppContext) -> None:
    h = await _onboarded(client, ctx)
    r = await client.get("/v1/me/footprint", headers=h)
    assert r.status_code == 200, r.text
    f = r.json()
    assert f["estimate"] is True and f["unit"] == "kg CO2"
    c = f["commute"]
    assert c["mode"] == "metro" and c["one_way_km"] > 0 and c["days_per_week"] >= 1
    w = c["week_kg"]
    assert 0 < w["low"] <= w["central"] <= w["high"]
    modes = [m["mode"] for m in c["modes"]]
    assert modes[-1] == "car"  # sorted by g/km: the car is the highest
    assert next(m for m in c["modes"] if m["current"])["mode"] == "metro"
    assert f["recorded"] is None  # recording is opt-in and off
    assert {s["year"] for s in f["sources"]} == {2014, 2015}


async def test_footprint_without_a_profile_is_empty(
    client: httpx.AsyncClient, ctx: AppContext
) -> None:
    h = await _session(client)
    f = (await client.get("/v1/me/footprint", headers=h)).json()
    assert f["commute"] is None and f["recorded"] is None
