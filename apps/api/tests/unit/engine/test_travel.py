"""Recorded travel (opt-in route recording): legs replace the declared day for their minutes."""

from datetime import datetime, time
from zoneinfo import ZoneInfo

import pytest

from lung.engine.config import EngineConfig
from lung.engine.day import build_day, travel_activity, travel_factor
from lung.engine.models import TravelLeg
from lung.engine.score import compute

from .conftest import ADULT_MAN, DAY, EXAMPLE_PLAN, EXAMPLE_READINGS, TZ, hourly

IST = ZoneInfo(TZ)


def _at(h: int, m: int = 0) -> datetime:
    return datetime.combine(DAY, time(h, m), tzinfo=IST)


def test_mode_mapping(cfg: EngineConfig) -> None:
    assert travel_activity("run", cfg) == "run"
    assert travel_activity("car", cfg) == "light"
    assert travel_activity("bus_metro", cfg) == "walk"
    assert travel_factor("walk", cfg) == 1.0
    assert travel_factor("car", cfg) == cfg.commute_factor["car"]


def test_leg_replaces_the_schedule_with_its_own_cell(cfg: EngineConfig) -> None:
    # An evening drive across town that the schedule knows nothing about (18:00-18:40 at home).
    leg = TravelLeg(_at(18), _at(18, 40), "far", "car")
    segs = build_day(DAY, EXAMPLE_PLAN, cfg, travel=[leg])
    drive = [s for s in segs if s.cell_id == "far"]
    assert len(drive) == 1
    d = drive[0]
    assert (d.place, d.activity, d.observed) == ("commute", "light", True)
    assert d.factor == cfg.commute_factor["car"]
    assert d.hours == pytest.approx(40 / 60)


def test_walk_leg_is_outdoor_air(cfg: EngineConfig) -> None:
    leg = TravelLeg(_at(19), _at(19, 30), "home", "walk")
    seg = next(s for s in build_day(DAY, EXAMPLE_PLAN, cfg, travel=[leg]) if s.observed)
    assert (seg.place, seg.activity, seg.factor) == ("commute", "walk", 1.0)


def test_future_legs_are_ignored(cfg: EngineConfig) -> None:
    leg = TravelLeg(_at(20), _at(20, 30), "far", "car")
    segs = build_day(DAY, EXAMPLE_PLAN, cfg, travel=[leg], now=_at(12))
    assert all(s.cell_id != "far" for s in segs)


def test_travel_through_dirty_air_raises_the_dose(cfg: EngineConfig) -> None:
    readings = {**EXAMPLE_READINGS, "far": hourly(400)}
    base = compute(ADULT_MAN, build_day(DAY, EXAMPLE_PLAN, cfg), readings, cfg)
    leg = TravelLeg(_at(18), _at(19), "far", "two_wheeler")
    trip = compute(ADULT_MAN, build_day(DAY, EXAMPLE_PLAN, cfg, travel=[leg]), readings, cfg)
    assert trip.dose_ug > base.dose_ug
    assert trip.split["commute"] > base.split["commute"]
