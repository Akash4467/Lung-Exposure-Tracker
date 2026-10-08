"""Opt-in route recording over HTTP: points in, legs out, today rescored, delete everything."""

from datetime import timedelta

import httpx
import pytest

from lung.services.context import AppContext
from lung.worker.handlers import HANDLERS

from .conftest import NOW, FakeQueue
from .test_api_app import _onboarded, _run_queued_fetches

pytestmark = pytest.mark.integration


async def _run_worker(ctx: AppContext) -> None:
    await _run_queued_fetches(ctx)
    q: FakeQueue = ctx.queue  # type: ignore[assignment]
    for _, body, _ in list(q.sent):
        if body["type"] == "recompute":
            await HANDLERS["recompute"](ctx, body)


def _points(start_min_ago: int) -> list[dict[str, object]]:
    """A 15-minute walk heading north from home, a point a minute, ending in the past."""
    t0 = NOW - timedelta(minutes=start_min_ago)
    return [
        {
            "t": (t0 + timedelta(minutes=i)).isoformat(),
            "lat": 28.6139 + 0.0007 * i,
            "lon": 77.2090,
            "accuracy": 12,
            "activity": "walking",
            "confidence": "high",
        }
        for i in range(16)
    ]


async def test_recorded_walk(client: httpx.AsyncClient, ctx: AppContext) -> None:
    h = await _onboarded(client, ctx)
    before = (await client.get("/v1/me/score/today", headers=h)).json()

    r = await client.post("/v1/me/tracks", json={"points": _points(60)}, headers=h)
    assert r.status_code == 202, r.text
    assert r.json() == {"points": 16, "legs": 1}

    day = (await client.get("/v1/me/tracks", headers=h)).json()
    (leg,) = day["legs"]
    assert leg["mode"] == "walk" and leg["source"] == "gps+activity"
    assert 1100 < leg["distance_m"] < 1250  # 15 × 0.0007° of latitude ≈ 1.17 km
    assert 2 <= len(leg["path"]) <= 30

    await _run_worker(ctx)
    after = (await client.get("/v1/me/score/today", headers=h)).json()
    assert after["by_activity"].get("walk", 0) > before["by_activity"].get("walk", 0)

    r = await client.delete("/v1/me/tracks", headers=h)
    assert r.status_code == 200 and r.json() == {"deleted": 1}
    assert (await client.get("/v1/me/tracks", headers=h)).json()["legs"] == []


async def test_track_validation(client: httpx.AsyncClient, ctx: AppContext) -> None:
    h = await _onboarded(client, ctx)
    old = _points(60 * 24 * 3)  # three days ago
    r = await client.post("/v1/me/tracks", json={"points": old}, headers=h)
    assert r.status_code == 400 and r.json()["error"]["code"] == "bad_point"
    r = await client.post("/v1/me/tracks", json={"points": []}, headers=h)
    assert r.status_code == 400
