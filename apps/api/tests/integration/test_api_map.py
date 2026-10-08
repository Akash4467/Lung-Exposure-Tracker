"""The world map over HTTP: the visible-area grid and any place's forecast, both cached."""

import httpx
import pytest

from lung.services.context import AppContext

from .test_api_app import _session

pytestmark = pytest.mark.integration


async def test_grid_anywhere_and_cached(client: httpx.AsyncClient, ctx: AppContext) -> None:
    h = await _session(client)  # signed in; no onboarding needed to browse the map
    box = {"south": 51.3, "west": -0.5, "north": 51.7, "east": 0.2}  # London
    r = await client.get("/v1/map/grid", params=box, headers=h)
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["step"] == 0.1 and body["estimated"] is True
    assert len(body["points"]) >= 20
    first = body["points"][0]
    assert first["pm25"] == pytest.approx(150 - first["lat"], abs=0.1)

    calls = len(ctx.air.calls)  # type: ignore[attr-defined]
    again = (await client.get("/v1/map/grid", params=box, headers=h)).json()
    assert again["points"] == body["points"]
    assert len(ctx.air.calls) == calls  # type: ignore[attr-defined]  # served from cache


async def test_grid_skips_points_without_data(client: httpx.AsyncClient) -> None:
    h = await _session(client)
    box = {"south": -75, "west": 0, "north": -50, "east": 20}
    pts = (await client.get("/v1/map/grid", params=box, headers=h)).json()["points"]
    assert pts and all(p["lat"] >= -60 for p in pts)


async def test_grid_validation(client: httpx.AsyncClient) -> None:
    h = await _session(client)
    r = await client.get(
        "/v1/map/grid", params={"south": 30, "west": 70, "north": 20, "east": 80}, headers=h
    )
    assert r.status_code == 400 and r.json()["error"]["code"] == "bad_bounds"
    r = await client.get("/v1/map/grid", params={"south": 1, "west": 1}, headers=h)
    assert r.status_code == 400  # missing north/east
    assert (await client.get("/v1/map/grid", params={})).status_code == 401


async def test_place_forecast(client: httpx.AsyncClient, ctx: AppContext) -> None:
    h = await _session(client)
    r = await client.get("/v1/map/place", params={"lat": 15.4909, "lon": 73.8278}, headers=h)
    assert r.status_code == 200, r.text
    p = r.json()
    assert (p["lat"], p["lon"]) == (15.5, 73.85)  # snapped to a ~5 km square
    assert p["now"]["pm25"] == 90.0  # 11:30 local
    assert len(p["days"]) >= 4
    for d in p["days"]:
        assert d["max_pm25"] >= d["avg_pm25"]
        assert len(d["best_hours"]) == 3
    # cleanest daytime hours are 13:30-15:30 local (08:00-10:00 UTC)
    assert sorted(h_[11:13] for h_ in p["days"][1]["best_hours"]) == ["08", "09", "10"]

    calls = len(ctx.air.calls)  # type: ignore[attr-defined]
    await client.get("/v1/map/place", params={"lat": 15.49, "lon": 73.83}, headers=h)
    assert len(ctx.air.calls) == calls  # type: ignore[attr-defined]  # same square, cached


async def test_route_planner(client: httpx.AsyncClient, ctx: AppContext) -> None:
    from .conftest import FakeRoutes
    from .test_api_app import _onboarded

    h = await _onboarded(client, ctx)
    ctx.routes = FakeRoutes()
    body = {"from_lat": 28.6139, "from_lon": 77.2090, "to_lat": 28.5355, "to_lon": 77.3910}
    r = await client.post("/v1/map/route", json=body, headers=h)
    assert r.status_code == 200, r.text
    plan = r.json()
    ids = [o["id"] for o in plan["options"]]
    assert ids == ["driving-car:0", "driving-car:1", "cycling-regular:0", "foot-walking:0"]
    fast, detour = plan["options"][0], plan["options"][1]
    # the fake's air is cleaner further north: the longer detour is the cleaner drive
    assert fast["fastest"] and not fast["cleanest"]
    assert detour["cleanest"] and detour["duration_min"] > fast["duration_min"]
    assert detour["avg_pm25"] < fast["avg_pm25"] and plan["cleaner_by_pct"] > 0
    assert all(len(p) == 3 for p in fast["path"])  # [lat, lon, roadside pm2.5]

    modes = {m["mode"]: m for m in plan["modes"]}
    assert set(modes) == {"car", "two_wheeler", "bus", "metro", "cycle", "walk"}
    assert modes["car"]["dose_ug"] < modes["two_wheeler"]["dose_ug"]  # cabin keeps some out
    assert modes["bus"]["duration_min"] > modes["car"]["duration_min"]
    assert plan["modes"][0]["dose_ug"] <= plan["modes"][-1]["dose_ug"]  # sorted
    assert plan["routes_from"] == "openrouteservice"


async def test_route_planner_without_a_routing_key(
    client: httpx.AsyncClient, ctx: AppContext
) -> None:
    from .test_api_app import _onboarded

    h = await _onboarded(client, ctx)  # ctx.routes is None: no ORS key
    body = {"from_lat": 28.6139, "from_lon": 77.2090, "to_lat": 28.5355, "to_lon": 77.3910}
    plan = (await client.post("/v1/map/route", json=body, headers=h)).json()
    assert plan["routes_from"] == "straight_line"
    assert [o["profile"] for o in plan["options"]] == [
        "driving-car",
        "cycling-regular",
        "foot-walking",
    ]
    assert all(o["duration_min"] > 0 and o["avg_pm25"] is not None for o in plan["options"])


async def test_route_planner_validation(client: httpx.AsyncClient, ctx: AppContext) -> None:
    from .test_api_app import _onboarded

    h = await _onboarded(client, ctx)
    same = {"from_lat": 28.6, "from_lon": 77.2, "to_lat": 28.6001, "to_lon": 77.2001}
    r = await client.post("/v1/map/route", json=same, headers=h)
    assert r.status_code == 400 and r.json()["error"]["code"] == "same_place"
    far = {"from_lat": 28.6, "from_lon": 77.2, "to_lat": 51.5, "to_lon": -0.1}
    r = await client.post("/v1/map/route", json=far, headers=h)
    assert r.status_code == 400 and r.json()["error"]["code"] == "too_far"
