"""Lung Load over HTTP: log a run, see it in the score, list and delete it, read the trends."""

from datetime import timedelta

import httpx
import pytest

from lung.services.context import AppContext

from .conftest import NOW
from .test_api_app import _onboarded

pytestmark = pytest.mark.integration

RUN_START = NOW - timedelta(hours=4, minutes=30)  # 07:00 in Delhi, at home before the commute


def _iv(start_offset_min: int, minutes: int, **extra: object) -> dict[str, object]:
    start = RUN_START + timedelta(minutes=start_offset_min)
    return {
        "start": start.isoformat(),
        "end": (start + timedelta(minutes=minutes)).isoformat(),
        **extra,
    }


async def test_logged_run_raises_the_dose_and_shows_by_activity(
    client: httpx.AsyncClient, ctx: AppContext
) -> None:
    h = await _onboarded(client, ctx)
    before = (await client.get("/v1/me/score/today", headers=h)).json()
    assert before["breathing_lpm"] and before["air_litres"]
    assert "run" not in before["by_activity"]

    r = await client.post(
        "/v1/me/activity", json={"activities": [_iv(0, 30, kind="run")]}, headers=h
    )
    assert r.status_code == 201, r.text
    (run_id,) = r.json()["ids"]

    after = (await client.get("/v1/me/score/today", headers=h)).json()
    assert after["dose_ug"] > before["dose_ug"]
    assert after["air_litres"] > before["air_litres"]
    assert after["by_activity"]["run"] > 0

    day = (await client.get("/v1/me/activity", headers=h)).json()
    assert [a["kind"] for a in day["activities"]] == ["run"]
    assert day["activities"][0]["id"] == run_id

    assert (await client.delete(f"/v1/me/activity/{run_id}", headers=h)).status_code == 204
    again = (await client.get("/v1/me/score/today", headers=h)).json()
    assert again["dose_ug"] == pytest.approx(before["dose_ug"], rel=1e-3)
    r = await client.delete(f"/v1/me/activity/{run_id}", headers=h)
    assert r.status_code == 404 and r.json()["error"]["code"] == "activity_not_found"


async def test_heart_rate_and_steps_become_exertion(
    client: httpx.AsyncClient, ctx: AppContext
) -> None:
    h = await _onboarded(client, ctx)
    r = await client.post(
        "/v1/me/activity",
        json={
            "activities": [
                _iv(0, 20, heart_rate=165, source="health_connect"),
                _iv(30, 20, steps_per_min=115, source="health_connect"),
            ]
        },
        headers=h,
    )
    assert r.status_code == 201, r.text
    acts = (await client.get("/v1/me/activity", headers=h)).json()["activities"]
    hr, steps = acts
    assert hr["kind"] == "run" and hr["met"] > 6  # 34-year-old at 165 bpm: vigorous
    assert steps["kind"] == "walk" and steps["met"] == pytest.approx(4.0, abs=0.01)


async def test_activity_validation(client: httpx.AsyncClient, ctx: AppContext) -> None:
    h = await _onboarded(client, ctx)
    bad = [
        _iv(0, 30),  # no kind, heart rate or steps
        {**_iv(0, 30, kind="run"), "start": (NOW - timedelta(days=3)).isoformat()},  # too old
        _iv(0, 13 * 60, kind="walk"),  # longer than 12 h
    ]
    for item in bad:
        r = await client.post("/v1/me/activity", json={"activities": [item]}, headers=h)
        assert r.status_code == 400, r.text
        assert r.json()["error"]["code"] == "bad_activity"
    r = await client.post(
        "/v1/me/activity", json={"activities": [_iv(0, 30, kind="swim")]}, headers=h
    )
    assert r.status_code == 400 and r.json()["error"]["code"] == "validation_failed"


async def test_history_and_insights(client: httpx.AsyncClient, ctx: AppContext) -> None:
    h = await _onboarded(client, ctx)
    await client.get("/v1/me/score/today", headers=h)
    r = await client.get("/v1/me/score/history", params={"days": 14}, headers=h)
    assert r.status_code == 200, r.text
    body = r.json()
    assert len(body["days"]) == 1 and body["days"][0]["date"] == "2026-10-04"
    ins = body["insights"]
    assert ins["days"] == 1
    assert ins["avg_score_7d"] == body["days"][0]["score"]
    assert ins["avg_score_prev_7d"] is None and ins["change_pct"] is None
    assert sum(ins["bands"].values()) == 1
    assert ins["avg_breathing_lpm"] > 5
    r = await client.get("/v1/me/score/history", params={"days": 91}, headers=h)
    assert r.status_code == 400 and r.json()["error"]["code"] == "validation_failed"


async def test_score_breakdown_adds_up(client: httpx.AsyncClient, ctx: AppContext) -> None:
    """What the app's "How is this worked out?" card shows must reproduce the score."""
    h = await _onboarded(client, ctx)
    s = (await client.get("/v1/me/score/today", headers=h)).json()
    assert s["ref_ug"] > 0 and s["sensitivity"] == 1.0  # a 34-year-old without a condition
    assert s["times_who"] == pytest.approx(s["score"] / 100, abs=0.05)
    assert 100 * s["dose_ug"] / s["ref_ug"] * s["sensitivity"] == pytest.approx(
        s["score"], rel=0.01
    )
    # the reference is the same day's air volume at 15 µg/m³
    assert s["ref_ug"] == pytest.approx(15 * s["air_litres"] / 1000, rel=0.01)


async def test_health_connect_resync_replaces(client: httpx.AsyncClient, ctx: AppContext) -> None:
    h = await _onboarded(client, ctx)
    batch = [
        _iv(0, 20, heart_rate=140, source="health_connect"),
        _iv(30, 15, steps_per_min=110, source="health_connect"),
    ]
    for _ in range(2):  # the phone sends the same hours twice
        r = await client.post("/v1/me/activity", json={"activities": batch}, headers=h)
        assert r.status_code == 201, r.text
    acts = (await client.get("/v1/me/activity", headers=h)).json()["activities"]
    assert len(acts) == 2

    met_default = next(a["met"] for a in acts if a["heart_rate"] == 140)

    # A fitter heart (lower resting rate) has a higher ceiling, so the same 140 bpm is more
    # work in absolute terms (Uth: VO2max ~ 15.3 x HRmax / HRrest): more air breathed.
    fit = [_iv(0, 20, heart_rate=140, resting_hr=50, source="health_connect")]
    await client.post("/v1/me/activity", json={"activities": fit}, headers=h)
    acts = (await client.get("/v1/me/activity", headers=h)).json()["activities"]
    assert len(acts) == 2  # replaced, not added
    met_fit = next(a["met"] for a in acts if a["heart_rate"] == 140)
    assert met_fit > met_default
