"""Smoke risk: FIRMS fires upwind of home raise tomorrow's flag; downwind or far ones don't."""

from datetime import timedelta

import httpx
import pytest

from lung.integrations.firms import FireDetection
from lung.services import fire_service
from lung.services.context import AppContext
from lung.worker.handlers import HANDLERS

from .conftest import NOW
from .test_api_app import _onboarded

pytestmark = pytest.mark.integration


class FakeFires:
    def __init__(self, fires: list[FireDetection]) -> None:
        self.fires_list = fires
        self.calls = 0

    async def fires(
        self, west: float, south: float, east: float, north: float, days: int
    ) -> list[FireDetection]:
        self.calls += 1
        return [f for f in self.fires_list if west <= f.lon <= east and south <= f.lat <= north]


def _cluster(lat: float, lon: float, n: int, conf: str = "nominal") -> list[FireDetection]:
    return [
        FireDetection(lat + i * 0.01, lon + i * 0.01, NOW - timedelta(hours=6), conf, 10.0)
        for i in range(n)
    ]


async def test_upwind_fires_raise_tomorrows_smoke_flag(
    client: httpx.AsyncClient, ctx: AppContext
) -> None:
    h = await _onboarded(client, ctx)  # home in Delhi; the fake wind blows from 300°
    before = (await client.get("/v1/me/score/forecast", headers=h)).json()
    assert before["fire_risk"] == "none"

    fires = (
        _cluster(30.7, 75.8, 30)  # Punjab, north-west of Delhi: upwind
        + _cluster(26.5, 79.5, 40)  # south-east of Delhi: downwind
        + _cluster(30.6, 75.9, 10, conf="low")  # upwind but low confidence: ignored
    )
    ctx.fires = FakeFires(fires)
    stored = await fire_service.refresh(ctx, force=True)
    assert stored == 80

    # 30 nominal upwind fires: "medium" (≥ 25), not "high" (≥ 100)
    await HANDLERS["recompute"](ctx, {"type": "recompute", "user_id": await _user_id(ctx)})
    after = (await client.get("/v1/me/score/forecast", headers=h)).json()
    assert after["fire_risk"] == "medium"


async def test_refresh_is_throttled_and_off_without_a_key(ctx: AppContext) -> None:
    assert await fire_service.refresh(ctx) == 0  # no FIRMS key in tests: nothing to do
    ctx.fires = FakeFires(_cluster(30.7, 75.8, 3))
    # nobody has places yet: nothing to fetch
    assert await fire_service.refresh(ctx, force=True) == 0


async def _user_id(ctx: AppContext) -> str:
    from sqlalchemy import text

    async with ctx.db.session() as s:
        return str((await s.execute(text("SELECT id FROM users LIMIT 1"))).scalar_one())
