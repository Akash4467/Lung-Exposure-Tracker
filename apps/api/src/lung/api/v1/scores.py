from typing import Annotated

from fastapi import APIRouter, Query

from lung.api.deps import Ctx, UserId
from lung.api.schemas.scores import (
    Brief,
    DayOut,
    HistoryOut,
    Insights,
    ScoreOut,
    SimulateIn,
    SimulateOut,
)
from lung.engine.models import Result
from lung.services import score_service

router = APIRouter(prefix="/v1/me/score", tags=["scores"])


@router.get("/today")
async def today(user_id: UserId, ctx: Ctx) -> ScoreOut:
    """Today's estimated exposure: score, likely range, band, split, tips."""
    return ScoreOut.from_row(await score_service.get_or_compute(ctx, user_id, is_forecast=False))


@router.get("/forecast")
async def forecast(user_id: UserId, ctx: Ctx) -> ScoreOut:
    """Tomorrow: forecast score, hour-by-hour outdoor PM2.5, best and worst hours, smoke risk."""
    return ScoreOut.from_row(await score_service.get_or_compute(ctx, user_id, is_forecast=True))


@router.get("/history")
async def history(
    user_id: UserId, ctx: Ctx, days: Annotated[int, Query(ge=1, le=90)] = 14
) -> HistoryOut:
    """Lung Load for the last `days` days (today included), with weekly insights."""
    h = await score_service.history(ctx, user_id, days)
    return HistoryOut(days=[DayOut.from_row(r) for r in h.days], insights=Insights(**h.insights))


def _brief(r: Result) -> Brief:
    return Brief(
        score=round(r.score),
        band=r.band,
        dose_ug=round(r.dose_ug, 1),
        cigarettes=round(r.cigarettes, 1),
    )


@router.post("/simulate")
async def simulate(body: SimulateIn, user_id: UserId, ctx: Ctx) -> SimulateOut:
    """What today would have been with a shifted commute and/or mitigations."""
    change = score_service.build_change(ctx, body.commute_shift_minutes, body.mitigations)
    res = await score_service.simulate_today(ctx, user_id, change)
    return SimulateOut(
        before=_brief(res.sim.before),
        after=_brief(res.sim.after),
        saves_pct=round(res.sim.saves_pct, 1),
        as_workday=res.as_workday,
    )
