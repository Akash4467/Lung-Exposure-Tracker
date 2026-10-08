"""Lung Load personalisation: measured exertion, running, and exercise outside near home."""

from dataclasses import replace
from datetime import datetime, time
from zoneinfo import ZoneInfo

import pytest

from lung.engine.activity import kind_from_met, met_from_cadence, met_from_heart_rate
from lung.engine.config import EngineConfig
from lung.engine.day import build_day
from lung.engine.dose import breathing_rate, typical_weight_kg
from lung.engine.models import ActivityInterval, Profile
from lung.engine.score import compute

from .conftest import ADULT_MAN, DAY, EXAMPLE_PLAN, EXAMPLE_READINGS, TZ, hourly

IST = ZoneInfo(TZ)


def _at(h: int, m: int = 0) -> datetime:
    return datetime.combine(DAY, time(h, m), tzinfo=IST)


# --- exertion from sensors ---------------------------------------------------------------


def test_resting_heart_rate_is_one_met(cfg: EngineConfig) -> None:
    assert met_from_heart_rate(70, 30, cfg) == pytest.approx(1.0)


def test_heart_rate_met_rises_with_effort_and_caps_at_max(cfg: EngineConfig) -> None:
    easy = met_from_heart_rate(100, 30, cfg)
    hard = met_from_heart_rate(160, 30, cfg)
    assert 1.0 < easy < hard
    hr_max = 208 - 0.7 * 30
    assert met_from_heart_rate(250, 30, cfg) == pytest.approx(met_from_heart_rate(hr_max, 30, cfg))
    # 15.3 × HRmax / 70 ml/kg/min at the top, i.e. ≈ 11.7 METs for a 30-year-old
    assert met_from_heart_rate(hr_max, 30, cfg) == pytest.approx(15.3 * hr_max / 70 / 3.5)


def test_same_heart_rate_is_closer_to_max_when_older(cfg: EngineConfig) -> None:
    # Older: lower max heart rate, so 140 bpm is a bigger share of what they can do.
    def share(age: int) -> float:
        top = met_from_heart_rate(250, age, cfg)
        return (met_from_heart_rate(140, age, cfg) - 1) / (top - 1)

    assert share(60) > share(20)


def test_cadence_points_and_interpolation(cfg: EngineConfig) -> None:
    assert met_from_cadence(100, cfg) == pytest.approx(3.0)
    assert met_from_cadence(130, cfg) == pytest.approx(5.0)
    assert met_from_cadence(115, cfg) == pytest.approx(4.0)
    assert met_from_cadence(0, cfg) == pytest.approx(1.3)
    assert met_from_cadence(400, cfg) == pytest.approx(10.0)


def test_kind_from_met(cfg: EngineConfig) -> None:
    assert kind_from_met(1.5, cfg) == "light"
    assert kind_from_met(3.5, cfg) == "walk"
    assert kind_from_met(3.5, cfg, moving=False) == "light"
    assert kind_from_met(9.0, cfg) == "run"


# --- breathing -------------------------------------------------------------------------------


def test_running_breathes_more_than_walking(cfg: EngineConfig) -> None:
    for p in (ADULT_MAN, replace(ADULT_MAN, weight_kg=70)):
        assert breathing_rate(p, "run", cfg) > breathing_rate(p, "walk", cfg)


def test_measured_met_overrides_activity(cfg: EngineConfig) -> None:
    hard = breathing_rate(ADULT_MAN, "light", cfg, met=8.0)
    assert hard == pytest.approx(breathing_rate(ADULT_MAN, "run", cfg, met=8.0))
    assert hard > breathing_rate(ADULT_MAN, "light", cfg)


def test_typical_weight(cfg: EngineConfig) -> None:
    assert typical_weight_kg(ADULT_MAN, cfg) == 65
    assert typical_weight_kg(Profile(age=30, sex="woman", sensitive=False), cfg) == 55
    assert typical_weight_kg(Profile(age=4, sex="other", sensitive=False), cfg) == 16
    assert typical_weight_kg(Profile(age=10, sex="man", sensitive=False), cfg) == 37
    assert typical_weight_kg(replace(ADULT_MAN, weight_kg=80), cfg) == 80


# --- the day ---------------------------------------------------------------------------------


def test_morning_run_near_home_is_outdoors_and_counts(cfg: EngineConfig) -> None:
    run = ActivityInterval(_at(7, 0), _at(7, 30), "run")
    segs = build_day(DAY, EXAMPLE_PLAN, cfg, activity=[run])
    ran = [s for s in segs if s.activity == "run"]
    assert len(ran) == 1
    assert ran[0].place == "home"
    assert ran[0].factor == 1.0  # outside, so no indoor protection
    assert ran[0].observed
    assert ran[0].hours == pytest.approx(0.5)

    base = compute(ADULT_MAN, build_day(DAY, EXAMPLE_PLAN, cfg), EXAMPLE_READINGS, cfg)
    with_run = compute(ADULT_MAN, segs, EXAMPLE_READINGS, cfg)
    assert with_run.dose_ug > base.dose_ug
    assert with_run.by_activity["run"] > 0.05
    assert sum(with_run.by_activity.values()) == pytest.approx(1.0)
    # an adult man breathes roughly 15-20 m3 a day; a half-hour run adds about 1 m3
    assert 12 < base.air_m3 < 22
    assert base.hours == pytest.approx(24)
    assert 8 < base.breathing_lpm < 16  # an adult resting/light day: roughly 10-13 L/min
    assert with_run.breathing_lpm > base.breathing_lpm
    assert with_run.air_m3 - base.air_m3 == pytest.approx(0.5 * (3.0 - 0.80), rel=0.25)


def test_indoor_workout_keeps_indoor_factor(cfg: EngineConfig) -> None:
    gym = ActivityInterval(_at(19, 0), _at(19, 45), "run", outdoors=False)
    segs = build_day(DAY, EXAMPLE_PLAN, cfg, activity=[gym])
    ran = next(s for s in segs if s.activity == "run")
    assert ran.factor < 1.0


def test_heart_rate_interval_carries_met(cfg: EngineConfig) -> None:
    iv = ActivityInterval(_at(18, 0), _at(18, 20), "light", met=4.2, outdoors=False)
    seg = next(s for s in build_day(DAY, EXAMPLE_PLAN, cfg, activity=[iv]) if s.met == 4.2)
    assert seg.hours == pytest.approx(1 / 3)


def test_future_activity_is_ignored(cfg: EngineConfig) -> None:
    run = ActivityInterval(_at(19, 0), _at(19, 30), "run")
    segs = build_day(DAY, EXAMPLE_PLAN, cfg, activity=[run], now=_at(12, 0))
    assert all(s.activity != "run" for s in segs)


def test_activity_on_commute_never_marks_outdoors_twice(cfg: EngineConfig) -> None:
    walk = ActivityInterval(_at(8, 30), _at(9, 0), "walk")
    segs = build_day(DAY, EXAMPLE_PLAN, cfg, activity=[walk])
    commute = [s for s in segs if s.place == "commute"]
    assert commute and all(s.activity == "walk" and s.factor == 1.0 for s in commute)


def test_clean_air_run_adds_little(cfg: EngineConfig) -> None:
    clean = {c: hourly(5) for c in ("home", "office", "commute")}
    run = ActivityInterval(_at(7, 0), _at(8, 0), "run")
    r = compute(ADULT_MAN, build_day(DAY, EXAMPLE_PLAN, cfg, activity=[run]), clean, cfg)
    assert r.band == "green"
