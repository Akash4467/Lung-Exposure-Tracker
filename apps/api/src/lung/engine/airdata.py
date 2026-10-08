"""Bend the gridded model towards nearby ground stations.

For each station, the error ratio is observed / model-at-the-station. Ratios are averaged in
log space with inverse-distance-squared weights, then shrunk towards "no correction" when
stations are few or far, and clamped. The corrected value is model × ratio.
"""

import math
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime

from lung.engine.config import EngineConfig


@dataclass(frozen=True)
class StationObs:
    distance_km: float  # from the cell centre
    observed: float  # station PM2.5, µg/m³
    model_at_station: float  # gridded model PM2.5 at the station's location, same hour


@dataclass(frozen=True)
class Correction:
    value: float
    ratio: float  # applied multiplier
    trust: float  # 0 = no station influence, → 1 = fully station-driven
    stations_used: int


def correct(model_value: float, stations: Sequence[StationObs], cfg: EngineConfig) -> Correction:
    ac = cfg.air_correction
    weights: list[float] = []
    logs: list[float] = []
    for s in stations:
        if s.distance_km > ac.radius_km or s.observed <= 0 or s.model_at_station <= 0:
            continue
        d = max(s.distance_km, ac.distance_floor_km)
        weights.append(1 / d**2)
        logs.append(math.log(s.observed / s.model_at_station))

    if not weights:
        return Correction(model_value, 1.0, 0.0, 0)

    total = sum(weights)
    mean_log = sum(w * lg for w, lg in zip(weights, logs, strict=True)) / total
    trust = total / (total + ac.prior_weight)
    limit = math.log(ac.max_ratio)
    ratio = math.exp(max(-limit, min(limit, mean_log * trust)))
    return Correction(model_value * ratio, ratio, trust, len(weights))


def correct_series(
    model: Mapping[datetime, float],
    stations_by_hour: Mapping[datetime, Sequence[StationObs]],
    cfg: EngineConfig,
) -> dict[datetime, float]:
    """Correct every hour of one cell; hours without station data are left as modelled."""
    return {
        hour: correct(value, stations_by_hour.get(hour, ()), cfg).value
        for hour, value in model.items()
    }
