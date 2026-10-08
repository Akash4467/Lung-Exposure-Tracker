"""Trips over HTTP: on trip days the day is spent at the destination, then back to normal."""

from datetime import timedelta

import httpx
import pytest
from sqlalchemy import text

from lung.domain.geo import cell_id
from lung.repositories import places as places_repo
from lung.repositories import trips as trips_repo
from lung.services.context import AppContext
from lung.worker.handlers import HANDLERS

from .conftest import NOW, FakeQueue
from .test_api_app import _onboarded, _run_queued_fetches

pytestmark = pytest.mark.integration

TODAY = (NOW + timedelta(hours=5, minutes=30)).date()  # local date in Delhi
GOA = {"label": "Goa", "lat": 15.4909, "lon": 73.8278}


async def _run_worker(ctx: AppContext) -> None:
    """What the worker would do next: fetch queued cells, then rescore queued users."""
    await _run_queued_fetches(ctx)
    q: FakeQueue = ctx.queue  # type: ignore[assignment]
    for _, body, _ in list(q.sent):
        if body["type"] == "recompute":
            await HANDLERS["recompute"](ctx, body)


async def test_trip_day_uses_the_destination(client: httpx.AsyncClient, ctx: AppContext) -> None:
    h = await _onboarded(client, ctx)
    before = (await client.get("/v1/me/score/today", headers=h)).json()
    assert before["trip"] is None
    assert before["split"]["commute"] > 0 and before["indoor_source_share"] > 0

    r = await client.post(
        "/v1/me/trips",
        json={**GOA, "start_date": str(TODAY), "end_date": str(TODAY + timedelta(days=3))},
        headers=h,
    )
    assert r.status_code == 201, r.text
    trip = r.json()
    assert trip["status"] == "now" and trip["days"] == 4

    goa_cell = cell_id(GOA["lat"], GOA["lon"], ctx.settings.cell_resolution_deg)
    async with ctx.db.session() as s:
        assert goa_cell in await places_repo.cells_in_use(s)  # the worker will keep it fresh
    await _run_worker(ctx)  # the destination's air arrives, then the day is rescored
    away = (await client.get("/v1/me/score/today", headers=h)).json()
    assert away["trip"] == {"id": trip["id"], "label": "Goa"}
    assert away["split"]["commute"] == 0  # a day off there: no commute
    assert away["indoor_source_share"] == 0  # and not the home's cooking smoke
    tomorrow = (await client.get("/v1/me/score/forecast", headers=h)).json()
    assert tomorrow["trip"]["label"] == "Goa"

    trips = (await client.get("/v1/me/trips", headers=h)).json()["trips"]
    assert [t["label"] for t in trips] == ["Goa"]

    assert (await client.delete(f"/v1/me/trips/{trip['id']}", headers=h)).status_code == 204
    back = (await client.get("/v1/me/score/today", headers=h)).json()
    assert back["trip"] is None and back["split"]["commute"] > 0
    r = await client.delete(f"/v1/me/trips/{trip['id']}", headers=h)
    assert r.status_code == 404 and r.json()["error"]["code"] == "trip_not_found"


async def test_future_trip_does_not_change_today(
    client: httpx.AsyncClient, ctx: AppContext
) -> None:
    h = await _onboarded(client, ctx)
    start = TODAY + timedelta(days=20)
    r = await client.post(
        "/v1/me/trips",
        json={**GOA, "start_date": str(start), "end_date": str(start + timedelta(days=2))},
        headers=h,
    )
    assert r.status_code == 201 and r.json()["status"] == "upcoming"
    assert (await client.get("/v1/me/score/today", headers=h)).json()["trip"] is None


async def test_trip_validation(client: httpx.AsyncClient, ctx: AppContext) -> None:
    h = await _onboarded(client, ctx)
    bad = [
        (TODAY + timedelta(days=3), TODAY + timedelta(days=1)),  # ends before it starts
        (TODAY - timedelta(days=9), TODAY - timedelta(days=5)),  # already over
        (TODAY, TODAY + timedelta(days=90)),  # too long
    ]
    for start, end in bad:
        r = await client.post(
            "/v1/me/trips", json={**GOA, "start_date": str(start), "end_date": str(end)}, headers=h
        )
        assert r.status_code == 400 and r.json()["error"]["code"] == "bad_trip", r.text


async def test_change_location_today(client: httpx.AsyncClient, ctx: AppContext) -> None:
    """The top-right location switch: somewhere else today, then back home."""
    h = await _onboarded(client, ctx)
    assert (await client.get("/v1/me/location", headers=h)).json() == {"kind": "home"}

    r = await client.post("/v1/me/location", json={"kind": "place", **GOA}, headers=h)
    assert r.status_code == 200, r.text
    assert r.json()["trip"]["days"] == 1
    # the destination's air is fetched on the spot, so today is rescored at once
    away = (await client.get("/v1/me/score/today", headers=h)).json()
    assert away["trip"]["label"] == "Goa" and away["split"]["commute"] == 0
    loc = (await client.get("/v1/me/location", headers=h)).json()
    assert loc["kind"] == "trip" and loc["trip"]["label"] == "Goa"

    r = await client.post("/v1/me/location", json={"kind": "home"}, headers=h)
    assert r.status_code == 200 and r.json() == {"kind": "home"}
    back = (await client.get("/v1/me/score/today", headers=h)).json()
    assert back["trip"] is None and back["split"]["commute"] > 0
    assert (await client.get("/v1/me/trips", headers=h)).json()["trips"] == []


async def test_going_home_keeps_the_days_already_away(
    client: httpx.AsyncClient, ctx: AppContext
) -> None:
    h = await _onboarded(client, ctx)
    start = TODAY - timedelta(days=1)
    r = await client.post(
        "/v1/me/trips",
        json={**GOA, "start_date": str(start), "end_date": str(TODAY + timedelta(days=4))},
        headers=h,
    )
    assert r.status_code == 201, r.text
    await client.post("/v1/me/location", json={"kind": "home"}, headers=h)
    async with ctx.db.session() as s:
        user = (
            await s.execute(text("SELECT id FROM users WHERE email = 'meera@example.com'"))
        ).scalar_one()
        rows = await trips_repo.ending_from(s, user, start)
    assert [(t.start_date, t.end_date) for t in rows] == [(start, start)]  # yesterday stays


async def test_location_validation(client: httpx.AsyncClient, ctx: AppContext) -> None:
    h = await _onboarded(client, ctx)
    r = await client.post("/v1/me/location", json={"kind": "place", "label": "x"}, headers=h)
    assert r.status_code == 400 and r.json()["error"]["code"] == "bad_location"
