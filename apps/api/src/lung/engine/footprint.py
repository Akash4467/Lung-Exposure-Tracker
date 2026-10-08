"""Commute footprint: estimated CO2 of a commute, against the other ways of making it.

Pure functions over footprint.yaml (parsed here, read by infra). CO2 is a climate measure:
it is not the PM2.5 behind Lung Load, so nothing here touches scores, and nothing should
call it "air pollution saved".

Every number is a range [low, central, high]. A saving counts as clear only when even the
pessimistic end (current mode's low vs the alternative's high) still saves something.
"""

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class Range:
    low: float
    central: float
    high: float

    def scale(self, k: float) -> "Range":
        return Range(self.low * k, self.central * k, self.high * k)

    def rounded(self, digits: int = 1) -> dict[str, float]:
        return {
            "low": round(self.low, digits),
            "central": round(self.central, digits),
            "high": round(self.high, digits),
        }


@dataclass(frozen=True)
class Source:
    id: str
    title: str
    publisher: str
    year: int
    url: str


@dataclass(frozen=True)
class FootprintConfig:
    factors: Mapping[str, Range]  # kg CO2 per passenger-km
    factor_source: Mapping[str, str]
    swap_days_per_week: int
    weeks_per_year: int
    max_walk_km: float
    max_cycle_km: float
    candidates: tuple[str, ...]
    sources: Mapping[str, Source]


def parse_footprint(raw: Mapping[str, Any]) -> FootprintConfig:
    factors = {
        m: Range(float(f["low"]), float(f["central"]), float(f["high"]))
        for m, f in raw["factors"].items()
    }
    for m, r in factors.items():
        if not (0 <= r.low <= r.central <= r.high):
            raise ValueError(f"footprint factor for {m} must be 0 <= low <= central <= high")
    s = raw["suggest"]
    return FootprintConfig(
        factors=factors,
        factor_source={m: f["source"] for m, f in raw["factors"].items() if "source" in f},
        swap_days_per_week=int(s["swap_days_per_week"]),
        weeks_per_year=int(s["weeks_per_year"]),
        max_walk_km=float(s["max_walk_km"]),
        max_cycle_km=float(s["max_cycle_km"]),
        candidates=tuple(s["candidates"]),
        sources={k: Source(id=k, **v) for k, v in raw["sources"].items()},
    )


@dataclass(frozen=True)
class ModeFootprint:
    mode: str
    per_km: Range
    week_kg: Range


@dataclass(frozen=True)
class Suggestion:
    mode: str
    days_per_week: int
    week_kg_saved: Range
    year_kg_saved: Range
    clear: bool  # saves something even at the pessimistic end of both ranges


@dataclass(frozen=True)
class Commute:
    mode: str
    one_way_km: float
    days_per_week: int
    week_km: float
    week_kg: Range
    year_kg: Range
    modes: tuple[ModeFootprint, ...]
    suggestion: Suggestion | None
    # what this commute avoids each week compared with driving it alone (None for drivers)
    vs_car_week_kg: Range | None


def _possible(mode: str, one_way_km: float, cfg: FootprintConfig) -> bool:
    if mode == "walk":
        return one_way_km <= cfg.max_walk_km
    if mode == "cycle":
        return one_way_km <= cfg.max_cycle_km
    return True


def saving(current: Range, alt: Range, km: float) -> Range:
    """kg saved by doing `km` on the alternative instead: pessimistic, central, optimistic."""
    return Range(
        (current.low - alt.high) * km,
        (current.central - alt.central) * km,
        (current.high - alt.low) * km,
    )


def commute(mode: str, one_way_km: float, days_per_week: int, cfg: FootprintConfig) -> Commute:
    week_km = 2 * one_way_km * days_per_week
    modes = tuple(
        ModeFootprint(m, f, f.scale(week_km))
        for m, f in cfg.factors.items()
        if m == mode or _possible(m, one_way_km, cfg)
    )
    current = cfg.factors[mode]
    swap_days = min(cfg.swap_days_per_week, days_per_week)
    swap_km = 2 * one_way_km * swap_days
    best: Suggestion | None = None
    for m in cfg.candidates:
        if m == mode or m not in cfg.factors or not _possible(m, one_way_km, cfg):
            continue
        week = saving(current, cfg.factors[m], swap_km)
        if week.central <= 0:
            continue
        s = Suggestion(m, swap_days, week, week.scale(cfg.weeks_per_year), clear=week.low > 0)
        # a clear saving beats a bigger but uncertain one
        if best is None or (s.clear, s.week_kg_saved.central) > (
            best.clear,
            best.week_kg_saved.central,
        ):
            best = s
    return Commute(
        mode=mode,
        one_way_km=one_way_km,
        days_per_week=days_per_week,
        week_km=week_km,
        week_kg=current.scale(week_km),
        year_kg=current.scale(week_km * cfg.weeks_per_year),
        modes=modes,
        suggestion=best if swap_days > 0 else None,
        vs_car_week_kg=None
        if mode == "car" or "car" not in cfg.factors
        else saving(cfg.factors["car"], current, week_km),
    )


@dataclass(frozen=True)
class Recorded:
    km_by_mode: Mapping[str, float]
    kg_by_mode: Mapping[str, Range]
    total_kg: Range


def recorded(legs: Sequence[tuple[str, float]], cfg: FootprintConfig) -> Recorded:
    """(mode, km) of recorded legs → kg per mode. Running counts as walking (no CO2)."""
    km: dict[str, float] = {}
    for mode, d in legs:
        m = "walk" if mode == "run" else mode
        if m in cfg.factors:
            km[m] = km.get(m, 0.0) + d
    kg = {m: cfg.factors[m].scale(d) for m, d in km.items()}
    total = Range(
        sum(r.low for r in kg.values()),
        sum(r.central for r in kg.values()),
        sum(r.high for r in kg.values()),
    )
    return Recorded(km, kg, total)
