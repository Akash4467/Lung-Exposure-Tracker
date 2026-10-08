"""Exertion (MET) from what a phone or wearable can measure. Pure functions; the numbers live
in config.yaml (`activity:`), with sources in docs/engine-parameters.md.

Heart rate: the share of heart-rate reserve used ≈ the share of oxygen-uptake reserve used
(Swain & Leutholtz). Max heart rate from age (Tanaka: 208 − 0.7 × age); aerobic capacity from
the max/resting heart-rate ratio (Uth: VO2max ≈ 15.3 × HRmax / HRrest ml/kg/min).

Steps: walking cadence maps to intensity (CADENCE-Adults: ~100 steps/min ≈ 3 METs,
~130 ≈ 5 METs), interpolated between configured points.
"""

from itertools import pairwise

from lung.engine.config import EngineConfig
from lung.engine.models import Activity

ML_O2_PER_MET = 3.5  # 1 MET = 3.5 ml O2 / kg / min


def met_from_heart_rate(
    heart_rate: float, age: int, cfg: EngineConfig, resting_hr: float | None = None
) -> float:
    a = cfg.activity
    rest = resting_hr or a.resting_hr_default
    hr_max = a.hr_max_intercept - a.hr_max_slope * age
    if hr_max <= rest:
        return 1.0
    reserve = min(max((heart_rate - rest) / (hr_max - rest), 0.0), 1.0)
    met_max = a.vo2max_factor * hr_max / rest / ML_O2_PER_MET
    return 1.0 + reserve * (met_max - 1.0)


def met_from_cadence(steps_per_min: float, cfg: EngineConfig) -> float:
    pts = cfg.activity.cadence_met
    if steps_per_min <= pts[0][0]:
        return pts[0][1]
    for (x0, y0), (x1, y1) in pairwise(pts):
        if steps_per_min <= x1:
            return y0 + (y1 - y0) * (steps_per_min - x0) / (x1 - x0)
    return pts[-1][1]


def kind_from_met(met: float, cfg: EngineConfig, moving: bool = True) -> Activity:
    """A label for display and splits when only the exertion is known."""
    t = cfg.activity.kind_thresholds
    if met >= t["run"]:
        return "run"
    if moving and met >= t["walk"]:
        return "walk"
    return "light"
