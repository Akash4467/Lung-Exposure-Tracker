"""How sure is the score? Monte Carlo over the uncertain inputs.

Each run multiplies the uncertain numbers by a log-normal draw (median 1) and recomputes the
day. Inputs the user has told us (weight, home size, purifier CADR, a station-corrected cell)
use the tighter spread, so every detail they add narrows the range.

The random generator is passed in, so a seeded generator gives the same answer every time.
"""

import math
import random
import statistics
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, replace
from datetime import date, datetime

from lung.engine.config import EngineConfig
from lung.engine.day import build_day
from lung.engine.models import (
    Activity,
    ActivityInterval,
    Band,
    DayPlan,
    IndoorState,
    Profile,
    Readings,
    TravelLeg,
    Visit,
)
from lung.engine.score import compute


@dataclass(frozen=True)
class Uncertainty:
    score_p10: float
    score_p50: float
    score_p90: float
    dose_p10_ug: float
    dose_p90_ug: float
    band_probability: dict[Band, float]
    runs: int


def _ln(rng: random.Random, sigma: float) -> float:
    return math.exp(rng.gauss(0.0, sigma)) if sigma > 0 else 1.0


def _perturbed(
    cfg: EngineConfig, plan: DayPlan, profile: Profile, rng: random.Random
) -> tuple[EngineConfig, DayPlan]:
    u = cfg.uncertainty
    ind = cfg.indoor

    # Breathing: per-activity draws (a uniform scale would cancel out of the score).
    personal = cfg.breathing_personal
    table: Mapping[Activity, Mapping[str, float]] = cfg.inhalation_m3_per_h
    if profile.weight_kg is not None:
        met = {k: v * _ln(rng, u.breathing_personal) for k, v in personal.met.items()}
        personal = replace(personal, met=met)
    else:
        drawn: dict[Activity, Mapping[str, float]] = {}
        for act, row in table.items():
            m = _ln(rng, u.breathing_table)
            drawn[act] = {who: v * m for who, v in row.items()}
        table = drawn

    size_known = plan.home_indoor.size is not None
    vol_m = _ln(rng, u.volume_known if size_known else u.volume_unknown)
    exch_m = _ln(rng, u.air_exchange)
    indoor = replace(
        ind,
        penetration=min(1.0, ind.penetration * _ln(rng, u.penetration)),
        deposition_per_h=ind.deposition_per_h * _ln(rng, u.deposition),
        air_exchange_per_h={k: v * exch_m for k, v in ind.air_exchange_per_h.items()},
        default_purifier_removal_per_h=ind.default_purifier_removal_per_h
        * _ln(rng, u.cadr_unknown),
        volume_m3={k: v * vol_m for k, v in ind.volume_m3.items()},
        sources={k: v * _ln(rng, u.source_emission) for k, v in ind.sources.items()},
    )
    masks = {
        k: v if k == "none" else min(1.0, v * _ln(rng, u.mask)) for k, v in cfg.mask_factor.items()
    }
    roads = {k: 1 + (v - 1) * _ln(rng, u.road) for k, v in cfg.road_factor.items()}
    new_cfg = replace(
        cfg,
        inhalation_m3_per_h=table,
        breathing_personal=personal,
        indoor=indoor,
        mask_factor=masks,
        road_factor=roads,
    )

    def cadr(state: IndoorState) -> IndoorState:
        if state.purifier_cadr_m3h is None:
            return state
        return replace(state, purifier_cadr_m3h=state.purifier_cadr_m3h * _ln(rng, u.cadr_known))

    new_plan = replace(
        plan, home_indoor=cadr(plan.home_indoor), office_indoor=cadr(plan.office_indoor)
    )
    return new_cfg, new_plan


def estimate_range(
    profile: Profile,
    local_date: date,
    plan: DayPlan,
    readings: Readings,
    cfg: EngineConfig,
    rng: random.Random,
    *,
    air_corrected: bool = False,
    visits: Sequence[Visit] = (),
    activity: Sequence[ActivityInterval] = (),
    travel: Sequence[TravelLeg] = (),
    now: datetime | None = None,
    runs: int | None = None,
) -> Uncertainty:
    n = runs or cfg.uncertainty.runs
    air_sigma = cfg.uncertainty.air_corrected if air_corrected else cfg.uncertainty.air_model

    scores: list[float] = []
    doses: list[float] = []
    bands: dict[Band, int] = {"green": 0, "amber": 0, "red": 0}
    for _ in range(n):
        run_cfg, run_plan = _perturbed(cfg, plan, profile, rng)
        air = _ln(rng, air_sigma)  # one draw for all cells: model errors are correlated
        run_readings = {c: {h: v * air for h, v in hrs.items()} for c, hrs in readings.items()}
        segments = build_day(
            local_date,
            run_plan,
            run_cfg,
            visits=visits,
            activity=activity,
            travel=travel,
            now=now,
        )
        r = compute(profile, segments, run_readings, run_cfg)
        scores.append(r.score)
        doses.append(r.dose_ug)
        bands[r.band] += 1

    s = statistics.quantiles(scores, n=10, method="inclusive")
    d = statistics.quantiles(doses, n=10, method="inclusive")
    return Uncertainty(
        score_p10=s[0],
        score_p50=s[4],
        score_p90=s[8],
        dose_p10_ug=d[0],
        dose_p90_ug=d[8],
        band_probability={b: c / n for b, c in bands.items()},
        runs=n,
    )
