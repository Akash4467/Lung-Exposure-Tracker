"""Indoor air as a steady-state mass balance.

    indoor = P·a/(a+k+c) × outdoor  +  Σ E / (V·(a+k+c))

P penetration, a air exchange (1/h, from the window state), k deposition (1/h),
c purifier removal = CADR/V (1/h), E source emission (µg/h), V volume (m³).

Using the steady state while a source runs gives the right *total* exposure for a
first-order system: the area under the concentration curve from a burst of mass M is
M/(V·(a+k+c)) however the burst is spread over time.
"""

from collections.abc import Iterable, Mapping
from typing import Literal

from lung.engine.config import EngineConfig
from lung.engine.models import IndoorState

IndoorPlace = Literal["home", "office"]

MG_PER_MIN_TO_UG_PER_H = 1000 * 60


def volume_m3(state: IndoorState, place: IndoorPlace, cfg: EngineConfig) -> float:
    ind = cfg.indoor
    default = ind.default_home_size if place == "home" else ind.default_office_size
    size = state.size if state.size is not None and state.size in ind.volume_m3 else default
    return ind.volume_m3[size]


def purifier_removal_per_h(state: IndoorState, place: IndoorPlace, cfg: EngineConfig) -> float:
    if not state.purifier:
        return 0.0
    if state.purifier_cadr_m3h is None:
        return cfg.indoor.default_purifier_removal_per_h
    return state.purifier_cadr_m3h / volume_m3(state, place, cfg)


def removal_per_h(state: IndoorState, place: IndoorPlace, cfg: EngineConfig) -> float:
    """a + k + c: how fast indoor PM2.5 is flushed, settled or filtered."""
    ind = cfg.indoor
    return (
        ind.air_exchange_per_h[state.windows]
        + ind.deposition_per_h
        + purifier_removal_per_h(state, place, cfg)
    )


def indoor_factor(state: IndoorState, cfg: EngineConfig, place: IndoorPlace = "home") -> float:
    """Share of outdoor PM2.5 present indoors."""
    ind = cfg.indoor
    a = ind.air_exchange_per_h[state.windows]
    return ind.penetration * a / removal_per_h(state, place, cfg)


def source_added_ugm3(
    kinds: Iterable[str],
    state: IndoorState,
    cfg: EngineConfig,
    place: IndoorPlace = "home",
    scales: Mapping[str, float] | None = None,
) -> float:
    """Extra PM2.5 (µg/m³) while these sources are running."""
    scales = scales or {}
    emission = (
        sum(cfg.indoor.sources[k] * scales.get(k, 1.0) for k in kinds) * MG_PER_MIN_TO_UG_PER_H
    )
    if emission == 0:
        return 0.0
    return emission / (volume_m3(state, place, cfg) * removal_per_h(state, place, cfg))
