"""The app's journey over HTTP: catalog → onboarding → score → change things → delete."""

from datetime import timedelta
from typing import Any

import httpx
import pytest

from lung.services.context import AppContext
from lung.worker.handlers import HANDLERS

from .conftest import NOW, FakeQueue

pytestmark = pytest.mark.integration

PROFILE: dict[str, Any] = {
    "age": 34,
    "sex": "woman",
    "sensitive": False,
    "weight_kg": 58,
    "timezone": "Asia/Kolkata",
    "places": {
        "home": {
            "label": "Home",
            "lat": 28.6139,
            "lon": 77.2090,
            "size": "2bhk",
            "sources": [{"kind": "cooking_lpg", "start": "19:30", "minutes": 45}],
        },
        "office": {"label": "Office", "lat": 28.5355, "lon": 77.3910},
    },
    "schedule": {
        "wake": "07:00",
        "leave_home": "08:30",
        "arrive_office": "09:00",
        "leave_office": "17:30",
        "arrive_home": "18:00",
        "sleep": "23:00",
        "commute_mode": "metro",
        "office_days": [1, 2, 3, 4, 5, 6, 7],
    },
}


async def _session(client: httpx.AsyncClient) -> dict[str, str]:
    r = await client.post(
        "/v1/auth/register", json={"email": "meera@example.com", "password": "long enough pw"}
    )
    return {"Authorization": f"Bearer {r.json()['access_token']}"}


async def _run_queued_fetches(ctx: AppContext) -> None:
    q: FakeQueue = ctx.queue  # type: ignore[assignment]
    for _, body, _ in list(q.sent):
        if body["type"] == "fetch":
            await HANDLERS["fetch"](ctx, body)


async def _onboarded(client: httpx.AsyncClient, ctx: AppContext) -> dict[str, str]:
    h = await _session(client)
    r = await client.put("/v1/me/profile", json=PROFILE, headers=h)
    assert r.status_code == 200, r.text
    await _run_queued_fetches(ctx)
    return h


async def test_catalog_is_public_and_comes_from_config(client: httpx.AsyncClient) -> None:
    c = (await client.get("/v1/catalog")).json()
    kinds = {s["kind"] for s in c["indoor_sources"]}
    assert {"cooking_lpg", "mosquito_coil", "smoking"} <= kinds
    assert "2bhk" in c["home_sizes"] and "office" not in c["home_sizes"]
    assert "source:mosquito_coil" in c["mitigations"]
    assert "not medical advice" in c["disclaimer"]


async def test_before_onboarding(client: httpx.AsyncClient) -> None:
    h = await _session(client)
    for path in ("/v1/me/profile", "/v1/me/score/today"):
        r = await client.get(path, headers=h)
        assert r.status_code == 404 and r.json()["error"]["code"] == "profile_incomplete"


async def test_onboarding_then_first_score(client: httpx.AsyncClient, ctx: AppContext) -> None:
    h = await _session(client)
    r = await client.put("/v1/me/profile", json=PROFILE, headers=h)
    assert r.status_code == 200, r.text
    saved = r.json()
    assert saved["places"]["home"]["cell_id"] == "28.6_77.2"
    assert saved["schedule"]["leave_home"] == "08:30"
    assert saved["places"]["home"]["sources"][0]["start"] == "19:30"
    assert (await client.get("/v1/auth/me", headers=h)).json()["onboarded"]

    # No air yet: a clear "come back in a minute", and the cells are being fetched.
    r = await client.get("/v1/me/score/today", headers=h)
    assert r.status_code == 503 and r.json()["error"]["code"] == "not_ready"
    assert r.headers["Retry-After"] == "60"

    await _run_queued_fetches(ctx)
    r = await client.get("/v1/me/score/today", headers=h)
    assert r.status_code == 200, r.text
    s = r.json()
    assert s["estimated"] is True and "not medical advice" in s["disclaimer"]
    assert s["band"] in {"green", "amber", "red"}
    assert s["range"]["p10"] <= s["score"] <= s["range"]["p90"]
    assert sum(s["split"].values()) == pytest.approx(1, abs=0.01)
    assert s["indoor_source_share"] > 0 and s["tips"]
    assert s["date"] == (NOW + timedelta(hours=5, minutes=30)).date().isoformat()

    f = (await client.get("/v1/me/score/forecast", headers=h)).json()
    assert f["is_forecast"] and len(f["hours"]) == 24 and f["fire_risk"] == "none"
    assert len(f["best_outdoor_hours"]) == 3


@pytest.mark.parametrize(
    ("patch", "code"),
    [
        ({"schedule": {**PROFILE["schedule"], "arrive_office": "08:00"}}, "bad_schedule"),
        (
            {
                "places": {
                    **PROFILE["places"],
                    "home": {
                        **PROFILE["places"]["home"],
                        "sources": [{"kind": "bonfire", "start": "20:00", "minutes": 30}],
                    },
                }
            },
            "unknown_source",
        ),
        (
            {
                "places": {
                    **PROFILE["places"],
                    "home": {**PROFILE["places"]["home"], "size": "castle"},
                }
            },
            "unknown_size",
        ),
        ({"timezone": "Mars/Olympus"}, "validation_failed"),
        ({"age": 2}, "validation_failed"),
        ({"weight_kg": 900}, "validation_failed"),
    ],
)
async def test_profile_validation(
    client: httpx.AsyncClient, patch: dict[str, Any], code: str
) -> None:
    h = await _session(client)
    r = await client.put("/v1/me/profile", json={**PROFILE, **patch}, headers=h)
    assert r.status_code == 400 and r.json()["error"]["code"] == code


async def test_indoor_change_updates_score(client: httpx.AsyncClient, ctx: AppContext) -> None:
    h = await _onboarded(client, ctx)
    before = (await client.get("/v1/me/score/today", headers=h)).json()["score"]
    r = await client.put(
        "/v1/me/indoor",
        json={"place": "home", "purifier": True, "purifier_cadr_m3h": 300},
        headers=h,
    )
    assert r.status_code == 200 and r.json()["purifier"] and r.json()["purifier_cadr_m3h"] == 300
    after = (await client.get("/v1/me/score/today", headers=h)).json()["score"]
    assert after < before

    r = await client.put("/v1/me/indoor", json={"place": "home", "sources": []}, headers=h)
    assert r.json()["sources"] == []


async def test_simulator(client: httpx.AsyncClient, ctx: AppContext) -> None:
    h = await _onboarded(client, ctx)
    r = await client.post(
        "/v1/me/score/simulate",
        json={"mitigations": ["purifier_home", "source:cooking_lpg"]},
        headers=h,
    )
    assert r.status_code == 200, r.text
    sim = r.json()
    assert sim["after"]["score"] < sim["before"]["score"] and sim["saves_pct"] > 0

    r = await client.post("/v1/me/score/simulate", json={"mitigations": ["magic"]}, headers=h)
    assert r.json()["error"]["code"] == "unknown_mitigation"
    r = await client.post("/v1/me/score/simulate", json={"commute_shift_minutes": 240}, headers=h)
    assert r.status_code == 400


async def test_commute_simulation_on_a_day_off_is_tried_as_a_workday(
    client: httpx.AsyncClient, ctx: AppContext
) -> None:
    h = await _session(client)
    weekend_off = {**PROFILE, "schedule": {**PROFILE["schedule"], "office_days": []}}
    assert (await client.put("/v1/me/profile", json=weekend_off, headers=h)).status_code == 200
    await _run_queued_fetches(ctx)
    r = await client.post("/v1/me/score/simulate", json={"mitigations": ["n95_commute"]}, headers=h)
    sim = r.json()
    assert sim["as_workday"] is True
    assert sim["after"]["dose_ug"] < sim["before"]["dose_ug"]
    r = await client.post(
        "/v1/me/score/simulate", json={"mitigations": ["purifier_home"]}, headers=h
    )
    assert r.json()["as_workday"] is False  # not a commute change: today as it is


async def test_visits_devices_and_air(client: httpx.AsyncClient, ctx: AppContext) -> None:
    h = await _onboarded(client, ctx)
    start = NOW - timedelta(hours=3)
    r = await client.post(
        "/v1/me/visits",
        json={
            "visits": [
                {
                    "place": "away",
                    "start": start.isoformat(),
                    "end": (start + timedelta(minutes=40)).isoformat(),
                    "activity": "walk",
                }
            ]
        },
        headers=h,
    )
    assert r.status_code == 202 and r.json() == {"accepted": 1}
    r = await client.post(
        "/v1/me/visits",
        json={
            "visits": [
                {
                    "place": "home",
                    "start": (NOW - timedelta(days=5)).isoformat(),
                    "end": (NOW - timedelta(days=4)).isoformat(),
                }
            ]
        },
        headers=h,
    )
    assert r.status_code == 400 and r.json()["error"]["code"] == "bad_visit"

    r = await client.post(
        "/v1/me/devices", json={"fcm_token": "fcm-token-abc123", "platform": "android"}, headers=h
    )
    assert r.status_code == 204
    assert (await client.delete("/v1/me/devices/fcm-token-abc123", headers=h)).status_code == 204

    r = await client.get("/v1/air", params={"lat": 28.6139, "lon": 77.2090}, headers=h)
    assert r.status_code == 200 and r.json()["cell_id"] == "28.6_77.2" and r.json()["hours"]
    r = await client.get("/v1/air", params={"lat": 12.97, "lon": 77.59}, headers=h)  # Bengaluru
    assert r.status_code == 503


async def test_delete_account(client: httpx.AsyncClient, ctx: AppContext) -> None:
    h = await _onboarded(client, ctx)
    assert (await client.delete("/v1/me", headers=h)).status_code == 204
    r = await client.get("/v1/auth/me", headers=h)  # token still signed, account gone
    assert r.status_code == 404


async def test_ready_reports_dependencies(client: httpx.AsyncClient) -> None:
    r = await client.get("/ready")
    assert r.status_code == 200
    assert r.json()["checks"] == {"database": True, "cache": True, "queue": True}


async def test_per_user_rate_limit(client: httpx.AsyncClient, ctx: AppContext) -> None:
    ctx.settings.rate_limit_per_user_per_min = 5
    h = await _session(client)
    codes = [(await client.get("/v1/auth/me", headers=h)).status_code for _ in range(7)]
    assert codes == [200] * 5 + [429, 429]


async def test_public_status_reports_air_freshness(
    client: httpx.AsyncClient, ctx: AppContext
) -> None:
    from lung.services import ingest_service

    await ctx.cache.delete("status:public")
    r = await client.get("/status")  # nothing fetched yet: the uptime check should fail
    assert (r.status_code, r.json()["status"]) == (503, "stale")

    ctx.settings.warm_areas = True
    await ingest_service.fetch(ctx, "28.6_77.2")  # central Delhi, a warm area
    await ctx.cache.delete("status:public")
    r = await client.get("/status")
    assert r.status_code == 200
    assert r.json() == {"status": "ok", "air_age_min": 0}
