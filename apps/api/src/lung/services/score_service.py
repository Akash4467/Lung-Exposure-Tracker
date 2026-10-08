"""Recompute a user's scores for today and tomorrow, and read them back."""

import hashlib
import random
from dataclasses import dataclass, replace
from datetime import UTC, date, datetime, timedelta
from typing import Any
from uuid import UUID
from zoneinfo import ZoneInfo

import structlog

from lung.domain.errors import InvalidInput, NotFound, TryLater
from lung.engine.day import build_day
from lung.engine.dose import MissingReadingError
from lung.engine.forecast import Forecast, forecast
from lung.engine.models import Change, Readings, Result
from lung.engine.score import compute
from lung.engine.tips import Simulation, Tip, simulate, tips
from lung.engine.uncertainty import Uncertainty, estimate_range
from lung.infra.engine_config import engine_version
from lung.repositories import air_readings as air_repo
from lung.repositories import daily_scores as scores_repo
from lung.repositories.daily_scores import ScoreRow
from lung.services import fire_service
from lung.services.context import AppContext
from lung.services.plan import (
    ProfileIncompleteError,
    UserInputs,
    load_activity,
    load_inputs,
    load_travel,
    load_visits,
)

log = structlog.get_logger()

MAX_GAP_H = 6  # fill a missing hour from a neighbour at most this far away
HOUR = timedelta(hours=1)


class NoAirDataError(LookupError):
    """Some cells the user needs have no usable readings yet."""

    def __init__(self, cells: list[str]) -> None:
        super().__init__(f"no air data for cells {cells}")
        self.cells = cells


@dataclass(frozen=True)
class Outcome:
    today: date
    tomorrow: date
    today_band: str
    tomorrow_band: str
    fire_risk: str


def score_cache_key(user_id: UUID, day: date, is_forecast: bool) -> str:
    return f"{'forecast' if is_forecast else 'score'}:{user_id}:{day.isoformat()}"


def fill_gaps(
    readings: dict[str, dict[datetime, float]], start: datetime, end: datetime
) -> dict[str, dict[datetime, float]]:
    """Fill each missing hour from the nearest reading within MAX_GAP_H (earlier first)."""
    out: dict[str, dict[datetime, float]] = {}
    for cell, hours in readings.items():
        filled = dict(hours)
        h = start.replace(minute=0, second=0, microsecond=0)
        while h < end:
            if h not in filled:
                for gap in range(1, MAX_GAP_H + 1):
                    near = hours.get(h - gap * HOUR, hours.get(h + gap * HOUR))
                    if near is not None:
                        filled[h] = near
                        break
            h += HOUR
        out[cell] = filled
    return out


def _seed(user_id: UUID, day: date) -> int:
    return int.from_bytes(hashlib.sha256(f"{user_id}:{day}".encode()).digest()[:8], "big")


def _trip_json(inputs: UserInputs, day: date) -> dict[str, Any]:
    trip = inputs.trip_on(day)
    return {"trip": {"id": trip.id, "label": trip.label}} if trip else {}


def _tip_json(t: Tip) -> dict[str, Any]:
    return {"id": t.id, "text": t.text, "saves_pct": t.saves_pct, "free": t.free}


def _row(
    day: date,
    is_forecast: bool,
    r: Result,
    u: Uncertainty,
    data_as_of: datetime,
    details: dict[str, Any],
    fire_risk: str | None,
) -> ScoreRow:
    return ScoreRow(
        date=day,
        is_forecast=is_forecast,
        dose_ug=r.dose_ug,
        score=r.score,
        score_p10=u.score_p10,
        score_p90=u.score_p90,
        band=r.band,
        cigarettes=r.cigarettes,
        avg_pm25=r.avg_pm25,
        home_share=r.split["home"],
        commute_share=r.split["commute"],
        office_share=r.split["office"],
        indoor_source_share=r.indoor_source_share,
        fire_risk=fire_risk,
        data_as_of=data_as_of,
        engine_version=engine_version(),
        details={
            **details,
            "band_probability": u.band_probability,
            "by_activity": r.by_activity,
            "air_m3": r.air_m3,
            "breathing_lpm": r.breathing_lpm,
            "ref_ug": r.ref_ug,  # the same day's breathing at the WHO guideline
            "sensitivity": sensitivity_of(r),
        },
    )


def sensitivity_of(r: Result) -> float:
    """M, recovered from the result: score = 100 × dose / ref × M."""
    return round(r.score * r.ref_ug / (100 * r.dose_ug), 3) if r.dose_ug > 0 else 1.0


def _forecast_details(f: Forecast) -> dict[str, Any]:
    def hours(items: list[Any]) -> list[dict[str, Any]]:
        return [{"start": h.start.isoformat(), "pm25": round(h.pm25, 1)} for h in items]

    return {
        "hours": hours(f.hours),
        "worst_hours": hours(f.worst_hours),
        "best_outdoor_hours": hours(f.best_outdoor_hours),
    }


async def _readings(
    ctx: AppContext, cells: list[str], start: datetime, end: datetime
) -> tuple[Readings, datetime]:
    async with ctx.db.session() as s:
        raw = await air_repo.pm25_for(s, cells, start, end)
        as_of = await air_repo.latest_fetch(s, cells)
    empty = [c for c, hours in raw.items() if not hours]
    if empty or as_of is None:
        raise NoAirDataError(empty or cells)
    return fill_gaps(raw, start, end), as_of


async def recompute(ctx: AppContext, user_id: UUID) -> Outcome:
    now = ctx.clock()
    async with ctx.db.session() as s:
        inputs = await load_inputs(s, user_id, ctx.settings.cell_resolution_deg)
    today = now.astimezone(ZoneInfo(inputs.tz)).date()
    tomorrow = today + timedelta(days=1)
    start, _ = inputs.local_day_window(today)
    _, end = inputs.local_day_window(tomorrow)
    async with ctx.db.session() as s:
        visits = await load_visits(s, user_id, *inputs.local_day_window(today))
        activity = await load_activity(s, user_id, *inputs.local_day_window(today))
        travel = await load_travel(s, user_id, *inputs.local_day_window(today))
    cells = sorted({*inputs.cells_for(today, tomorrow), *(leg.cell_id for leg in travel)})
    readings, as_of = await _readings(ctx, cells, start, end)
    async with ctx.db.session() as s:
        corrected = await air_repo.has_source(
            s, inputs.home.cell_id, *inputs.local_day_window(today), "open_meteo+stations"
        )

    cfg, runs = ctx.cfg, ctx.settings.uncertainty_runs
    plan_today, plan_tomorrow = inputs.plan_for(today), inputs.plan_for(tomorrow)
    upwind = await fire_service.upwind_count(
        ctx, plan_tomorrow.home_cell, *inputs.local_day_window(tomorrow)
    )
    try:
        segments = build_day(
            today, plan_today, cfg, visits=visits, activity=activity, travel=travel, now=now
        )
        r_today = compute(inputs.profile, segments, readings, cfg)
        u_today = estimate_range(
            inputs.profile,
            today,
            plan_today,
            readings,
            cfg,
            random.Random(_seed(user_id, today)),  # noqa: S311  sampling, not security
            air_corrected=corrected,
            visits=visits,
            activity=activity,
            travel=travel,
            now=now,
            runs=runs,
        )
        today_tips = tips(inputs.profile, today, plan_today, readings, cfg)
        fc = forecast(inputs.profile, tomorrow, plan_tomorrow, readings, cfg, upwind_fires=upwind)
        u_tomorrow = estimate_range(
            inputs.profile,
            tomorrow,
            plan_tomorrow,
            readings,
            cfg,
            random.Random(_seed(user_id, tomorrow)),  # noqa: S311
            runs=runs,
        )
    except MissingReadingError as e:
        raise NoAirDataError([e.cell_id]) from e

    async with ctx.db.session() as s:
        await scores_repo.upsert(
            s,
            user_id,
            _row(
                today,
                False,
                r_today,
                u_today,
                as_of,
                {"tips": [_tip_json(t) for t in today_tips], **_trip_json(inputs, today)},
                None,
            ),
        )
        await scores_repo.upsert(
            s,
            user_id,
            _row(
                tomorrow,
                True,
                fc.result,
                u_tomorrow,
                as_of,
                {**_forecast_details(fc), **_trip_json(inputs, tomorrow)},
                fc.fire_risk,
            ),
        )
    await ctx.cache.delete(
        score_cache_key(user_id, today, False), score_cache_key(user_id, tomorrow, True)
    )
    log.info("recomputed", user_id=str(user_id), today=r_today.band, tomorrow=fc.result.band)
    return Outcome(today, tomorrow, r_today.band, fc.result.band, fc.fire_risk)


async def get_score(
    ctx: AppContext, user_id: UUID, day: date, is_forecast: bool
) -> ScoreRow | None:
    """Cache first, then the database. Returns None if not computed yet."""
    key = score_cache_key(user_id, day, is_forecast)
    cached = await ctx.cache.get_json(key)
    if cached is not None:
        cached["date"] = date.fromisoformat(cached["date"])
        cached["data_as_of"] = datetime.fromisoformat(cached["data_as_of"])
        if cached.get("computed_at"):
            cached["computed_at"] = datetime.fromisoformat(cached["computed_at"])
        return ScoreRow(**cached)
    async with ctx.db.session() as s:
        row = await scores_repo.get(s, user_id, day, is_forecast)
    if row is not None:
        await ctx.cache.set_json(key, row.__dict__, ctx.settings.score_cache_ttl_s)
    return row


def local_today(tz: str, now: datetime | None = None) -> date:
    return (now or datetime.now(UTC)).astimezone(ZoneInfo(tz)).date()


async def get_or_compute(ctx: AppContext, user_id: UUID, is_forecast: bool) -> ScoreRow:
    """Today's (or tomorrow's) stored score; computed on the spot if missing or stale."""
    async with ctx.db.session() as s:
        try:
            inputs = await load_inputs(s, user_id, ctx.settings.cell_resolution_deg)
        except ProfileIncompleteError as e:
            raise NotFound("finish onboarding first", "profile_incomplete") from e
    day = local_today(inputs.tz, ctx.clock()) + timedelta(days=1 if is_forecast else 0)
    row = await get_score(ctx, user_id, day, is_forecast)
    if row is None:
        try:
            await recompute(ctx, user_id)
        except NoAirDataError as e:
            await ctx.queue.send_many(
                ctx.settings.sqs_ingest_url,
                [{"type": "fetch", "cell_id": c, "force": True} for c in e.cells],
            )
            raise TryLater("air data for your area is still loading", 60) from e
        row = await get_score(ctx, user_id, day, is_forecast)
    if row is None:  # pragma: no cover - recompute always writes both days
        raise TryLater("score not ready", 30)
    return row


MITIGATIONS = ("purifier_home", "purifier_office", "close_windows_home", "n95_commute")


def build_change(ctx: AppContext, shift_minutes: int, mitigations: list[str]) -> Change:
    """Turns the simulator's controls into one engine Change. `source:<kind>` applies that
    source's tip (e.g. source:mosquito_coil)."""
    if not -180 <= shift_minutes <= 180:
        raise InvalidInput("commute shift must be within ±3 hours", "bad_shift")
    tips_cfg = ctx.cfg.indoor.source_tips
    scale: list[tuple[str, float]] = []
    for m in mitigations:
        if m.startswith("source:") and m.removeprefix("source:") in tips_cfg:
            kind = m.removeprefix("source:")
            scale.append((kind, tips_cfg[kind].scale))
        elif m not in MITIGATIONS:
            raise InvalidInput(f"unknown mitigation {m!r}", "unknown_mitigation")
    return Change(
        commute_shift_minutes=shift_minutes,
        purifier_home="purifier_home" in mitigations,
        purifier_office="purifier_office" in mitigations,
        close_windows_home="close_windows_home" in mitigations,
        commute_mask="n95" if "n95_commute" in mitigations else None,
        scale_sources=tuple(scale),
    )


@dataclass(frozen=True)
class TodaySimulation:
    sim: Simulation
    as_workday: bool  # today is a day off, so the commute change was tried as a workday


async def simulate_today(ctx: AppContext, user_id: UUID, change: Change) -> TodaySimulation:
    """What today would have scored with the change. Computed live, never stored.

    On a day off a commute change would do nothing, so it is tried on today's air as if
    today were a workday, and the result says so."""
    async with ctx.db.session() as s:
        try:
            inputs = await load_inputs(s, user_id, ctx.settings.cell_resolution_deg)
        except ProfileIncompleteError as e:
            raise NotFound("finish onboarding first", "profile_incomplete") from e
    today = local_today(inputs.tz, ctx.clock())
    start, end = inputs.local_day_window(today)
    try:
        readings, _ = await _readings(ctx, inputs.cells_for(today), start, end)
        plan = inputs.plan_for(today)
        touches_commute = bool(change.commute_shift_minutes) or change.commute_mask is not None
        as_workday = touches_commute and not plan.goes_to_office
        if as_workday:
            plan = replace(plan, goes_to_office=True)
        sim = simulate(inputs.profile, today, plan, change, readings, ctx.cfg)
        return TodaySimulation(sim, as_workday)
    except (NoAirDataError, MissingReadingError) as e:
        raise TryLater("air data for your area is still loading", 60) from e
    except ValueError as e:  # the shift pushes a trip past midnight
        raise InvalidInput(str(e), "bad_shift") from e


def catalog(ctx: AppContext) -> dict[str, Any]:
    """Every option the app can offer, straight from config, so adding a source kind or a
    home size in config.yaml shows up in the app with no code change."""
    ind = ctx.cfg.indoor
    return {
        "indoor_sources": [
            {"kind": k, "tip": ind.source_tips[k].text if k in ind.source_tips else None}
            for k in ind.sources
        ],
        "home_sizes": [k for k in ind.volume_m3 if k != "office"],
        "windows": list(ind.air_exchange_per_h),
        "commute_modes": list(ctx.cfg.commute_activity),
        "masks": list(ctx.cfg.mask_factor),
        "mitigations": [*MITIGATIONS, *(f"source:{k}" for k in ind.source_tips)],
        "bands": {"green_max": ctx.cfg.bands.green_max, "amber_max": ctx.cfg.bands.amber_max},
        "disclaimer": "Estimated exposure. Informational only, not medical advice.",
        "engine_version": engine_version(),
    }


EXERCISE = ("walk", "run", "cycle")


@dataclass(frozen=True)
class History:
    days: list[ScoreRow]
    insights: dict[str, Any]


def insights(days: list[ScoreRow], today: date) -> dict[str, Any]:
    """Plain numbers for the Trends screen: this week against last week, best and worst days,
    how much of the dose came while exercising. The app words them."""

    def mean(xs: list[float]) -> float | None:
        return sum(xs) / len(xs) if xs else None

    this_week = [d.score for d in days if (today - d.date).days < 7]
    last_week = [d.score for d in days if 7 <= (today - d.date).days < 14]
    now, before = mean(this_week), mean(last_week)
    exercise = [
        sum((d.details or {}).get("by_activity", {}).get(a, 0.0) for a in EXERCISE) for d in days
    ]
    lpm = [x for d in days if (x := (d.details or {}).get("breathing_lpm"))]
    bands = {b: sum(d.band == b for d in days) for b in ("green", "amber", "red")}
    worst = max(days, key=lambda d: d.score, default=None)
    best = min(days, key=lambda d: d.score, default=None)
    return {
        "days": len(days),
        "avg_score_7d": round(now) if now is not None else None,
        "avg_score_prev_7d": round(before) if before is not None else None,
        "change_pct": round(100 * (now - before) / before, 1) if now and before else None,
        "bands": bands,
        "worst_day": {"date": worst.date, "score": round(worst.score)} if worst else None,
        "best_day": {"date": best.date, "score": round(best.score)} if best else None,
        "exercise_share": round(sum(exercise) / len(exercise), 3) if exercise else 0.0,
        "avg_breathing_lpm": round(sum(lpm) / len(lpm), 1) if lpm else None,
    }


async def history(ctx: AppContext, user_id: UUID, days: int) -> History:
    """The last `days` days of stored scores (today included) and the weekly insights."""
    if not 1 <= days <= 90:
        raise InvalidInput("days must be between 1 and 90", "bad_days")
    async with ctx.db.session() as s:
        try:
            inputs = await load_inputs(s, user_id, ctx.settings.cell_resolution_deg)
        except ProfileIncompleteError as e:
            raise NotFound("finish onboarding first", "profile_incomplete") from e
        today = local_today(inputs.tz, ctx.clock())
        rows = await scores_repo.between(s, user_id, today - timedelta(days=days - 1), today)
    return History(rows, insights(rows, today))
