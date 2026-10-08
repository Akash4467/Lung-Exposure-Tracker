"""Tests for the accuracy refinements: stations, route, indoor model, geofence visits,
personal breathing, nowcast and fire risk, and the uncertainty range."""

import math
import random
from dataclasses import replace
from datetime import UTC, datetime, time, timedelta
from zoneinfo import ZoneInfo

import pytest

from lung.engine.airdata import StationObs, correct, correct_series
from lung.engine.config import EngineConfig
from lung.engine.day import build_day
from lung.engine.dose import breathing_rate
from lung.engine.forecast import fire_risk, forecast, nowcast
from lung.engine.indoor import indoor_factor, source_added_ugm3
from lung.engine.models import IndoorState, Profile, RoutePoint, Segment, SourceUse, Visit
from lung.engine.score import compute
from lung.engine.uncertainty import estimate_range

from .conftest import ADULT_MAN, DAY, EXAMPLE_PLAN, EXAMPLE_READINGS, TZ, hourly

IST = ZoneInfo(TZ)


def local(h: int, m: int = 0) -> datetime:
    return datetime.combine(DAY, time(h, m), tzinfo=IST)


def _shape(segs: list[Segment]) -> list[tuple[str, str, str]]:
    return [(s.place, s.start.strftime("%H:%M"), s.end.strftime("%H:%M")) for s in segs]


# ------------------------------------------------------------------ 1. station correction


class TestStationCorrection:
    def test_no_stations_leaves_model_alone(self, cfg: EngineConfig) -> None:
        c = correct(100, [], cfg)
        assert (c.value, c.ratio, c.trust, c.stations_used) == (100, 1.0, 0.0, 0)

    def test_close_station_pulls_model_almost_all_the_way(self, cfg: EngineConfig) -> None:
        # Station 1 km away reads double what the model says there.
        c = correct(100, [StationObs(1.0, observed=200, model_at_station=100)], cfg)
        assert c.trust == pytest.approx(1 / 1.01)
        assert c.value == pytest.approx(100 * 2 ** (1 / 1.01))

    def test_far_station_has_less_pull(self, cfg: EngineConfig) -> None:
        near = correct(100, [StationObs(3, 200, 100)], cfg)
        far = correct(100, [StationObs(20, 200, 100)], cfg)
        assert 100 < far.value < near.value

    def test_station_beyond_radius_ignored(self, cfg: EngineConfig) -> None:
        assert correct(100, [StationObs(31, 400, 100)], cfg).stations_used == 0

    def test_ratio_is_clamped(self, cfg: EngineConfig) -> None:
        assert correct(100, [StationObs(1, 10_000, 10)], cfg).value == pytest.approx(400)

    def test_series_corrects_only_hours_with_stations(self, cfg: EngineConfig) -> None:
        h1, h2 = datetime(2026, 10, 3, 1, tzinfo=UTC), datetime(2026, 10, 3, 2, tzinfo=UTC)
        out = correct_series({h1: 100, h2: 100}, {h1: [StationObs(1, 150, 100)]}, cfg)
        assert out[h1] > 100
        assert out[h2] == 100


# ------------------------------------------------------------------ 2. route-aware commute

ROUTE = (RoutePoint("r1", "primary"), RoutePoint("r2", "residential"))


def test_commute_is_split_along_the_route_and_reversed_home(cfg: EngineConfig) -> None:
    segs = build_day(DAY, replace(EXAMPLE_PLAN, route=ROUTE), cfg)
    commute = [
        (s.cell_id, s.factor, s.start.strftime("%H:%M")) for s in segs if s.place == "commute"
    ]
    assert commute == [
        ("r1", 1.2, "08:30"),
        ("r2", 1.0, "08:45"),
        ("r2", 1.0, "17:00"),
        ("r1", 1.2, "17:15"),
    ]
    assert sum(s.hours for s in segs) == pytest.approx(24)


def test_busy_road_raises_the_dose(cfg: EngineConfig) -> None:
    readings = dict(EXAMPLE_READINGS) | {"r1": hourly(200), "r2": hourly(200)}
    plain = compute(ADULT_MAN, build_day(DAY, EXAMPLE_PLAN, cfg), readings, cfg)
    routed = compute(
        ADULT_MAN, build_day(DAY, replace(EXAMPLE_PLAN, route=ROUTE), cfg), readings, cfg
    )
    assert routed.dose_ug > plain.dose_ug


# ------------------------------------------------------------------ 3. indoor model


class TestIndoorModel:
    def test_defaults_reproduce_design_doc_factors(self, cfg: EngineConfig) -> None:
        assert indoor_factor(IndoorState("closed"), cfg) == pytest.approx(0.4, rel=1e-5)
        assert indoor_factor(IndoorState("normal"), cfg) == pytest.approx(0.5, rel=1e-5)
        assert indoor_factor(IndoorState("open"), cfg) == pytest.approx(0.7, rel=1e-5)

    def test_known_cadr_and_size(self, cfg: EngineConfig) -> None:
        # 210 m³/h in a 210 m³ 2BHK removes 1.0 per hour.
        s = IndoorState("normal", purifier=True, purifier_cadr_m3h=210, size="2bhk")
        assert indoor_factor(s, cfg) == pytest.approx(0.8 * (2 / 3) / (2 / 3 + 0.4 + 1.0), rel=1e-5)

    def test_cooking_adds_pm_scaled_by_volume_and_ventilation(self, cfg: EngineConfig) -> None:
        base = source_added_ugm3(["cooking_lpg"], IndoorState(), cfg)
        assert base == pytest.approx(60_000 / (210 * (2 / 3 + 0.4)), rel=1e-5)
        assert source_added_ugm3(["cooking_lpg"], IndoorState(size="1bhk"), cfg) > base
        assert source_added_ugm3(["cooking_lpg"], IndoorState("open"), cfg) < base
        assert source_added_ugm3(["cooking_lpg"], IndoorState(purifier=True), cfg) < base
        assert source_added_ugm3(["cooking_biomass"], IndoorState(), cfg) == pytest.approx(
            15 * base
        )

    def test_source_window_splits_home_time_and_raises_dose(self, cfg: EngineConfig) -> None:
        cooking = IndoorState(sources=(SourceUse("cooking_lpg", time(19, 30), 45),))
        plan = replace(EXAMPLE_PLAN, home_indoor=cooking)
        segs = build_day(DAY, plan, cfg)
        assert ("home", "19:30", "20:15") in _shape(segs)
        r = compute(ADULT_MAN, segs, EXAMPLE_READINGS, cfg)
        base = compute(ADULT_MAN, build_day(DAY, EXAMPLE_PLAN, cfg), EXAMPLE_READINGS, cfg)
        assert r.dose_ug > base.dose_ug
        assert r.indoor_source_share > 0
        assert base.indoor_source_share == 0

    def test_overnight_coil_wraps_midnight(self, cfg: EngineConfig) -> None:
        coil = IndoorState(sources=(SourceUse("mosquito_coil", time(22, 0), 8 * 60),))
        segs = build_day(DAY, replace(EXAMPLE_PLAN, home_indoor=coil), cfg)
        burning = [s for s in segs if s.added_ugm3 > 0]
        assert [(s.start.strftime("%H:%M"), s.end.strftime("%H:%M")) for s in burning] == [
            ("00:00", "06:00"),
            ("22:00", "00:00"),
        ]
        assert {s.activity for s in burning} == {"asleep", "light"}

    def test_sources_only_count_while_at_home(self, cfg: EngineConfig) -> None:
        lunch = IndoorState(sources=(SourceUse("cooking_lpg", time(13, 0), 60),))
        segs = build_day(DAY, replace(EXAMPLE_PLAN, home_indoor=lunch), cfg)
        assert all(s.added_ugm3 == 0 for s in segs)  # at the office 09:00-17:00

    def test_unknown_source_kind_rejected(self, cfg: EngineConfig) -> None:
        bad = IndoorState(sources=(SourceUse("bonfire", time(20, 0), 30),))
        with pytest.raises(ValueError, match="unknown indoor source"):
            build_day(DAY, replace(EXAMPLE_PLAN, home_indoor=bad), cfg)


# ------------------------------------------------------------------ 4. geofence visits


class TestVisits:
    VISITS = (
        Visit("home", local(0), local(9, 30)),
        Visit("away", local(9, 30), local(10), activity="walk"),
        Visit("office", local(10), local(18)),  # runs past `now`
    )

    def test_observed_past_replaces_schedule_future_stays_declared(self, cfg: EngineConfig) -> None:
        segs = build_day(DAY, EXAMPLE_PLAN, cfg, visits=self.VISITS, now=local(12))
        shape = [(p, a, b, s.observed) for (p, a, b), s in zip(_shape(segs), segs, strict=True)]
        assert shape[:4] == [
            ("home", "00:00", "07:00", True),  # declared sleep kept while home
            ("home", "07:00", "09:30", True),  # stayed home late
            ("commute", "09:30", "10:00", True),
            ("office", "10:00", "12:00", True),
        ]
        assert ("office", "12:00", "17:00", False) in shape  # after now: the schedule
        assert sum(s.hours for s in segs) == pytest.approx(24)

    def test_walking_away_is_outdoor_even_for_car_commuters(self, cfg: EngineConfig) -> None:
        car = replace(EXAMPLE_PLAN, schedule=replace(EXAMPLE_PLAN.schedule, commute_mode="car"))
        segs = build_day(DAY, car, cfg, visits=self.VISITS, now=local(12))
        walk = next(s for s in segs if s.observed and s.place == "commute")
        assert (walk.activity, walk.factor) == ("walk", 1.0)

    def test_no_now_means_whole_day_can_be_observed(self, cfg: EngineConfig) -> None:
        segs = build_day(DAY, EXAMPLE_PLAN, cfg, visits=(Visit("home", local(0), local(23, 59)),))
        assert {s.place for s in segs} == {"home"}


# ------------------------------------------------------------------ 5. personal breathing


class TestPersonalBreathing:
    def test_adult_man_matches_table_magnitude(self, cfg: EngineConfig) -> None:
        p = Profile(35, "man", False, weight_kg=70)
        bmr_per_h = (11.6 * 70 + 879) / 24
        assert breathing_rate(p, "light", cfg) == pytest.approx(bmr_per_h * 2.0 * 0.209 * 27 / 1000)
        assert breathing_rate(p, "light", cfg) == pytest.approx(0.8, abs=0.05)
        assert breathing_rate(p, "walk", cfg) == pytest.approx(1.4, abs=0.05)

    def test_heavier_person_breathes_more(self, cfg: EngineConfig) -> None:
        light = breathing_rate(Profile(35, "woman", False, weight_kg=50), "walk", cfg)
        heavy = breathing_rate(Profile(35, "woman", False, weight_kg=90), "walk", cfg)
        assert heavy > light

    def test_other_averages_and_weight_overrides_child_table(self, cfg: EngineConfig) -> None:
        man = breathing_rate(Profile(40, "man", False, 70), "light", cfg)
        woman = breathing_rate(Profile(40, "woman", False, 70), "light", cfg)
        assert breathing_rate(Profile(40, "other", False, 70), "light", cfg) == pytest.approx(
            (man + woman) / 2
        )
        child = breathing_rate(Profile(8, "man", False, 25), "light", cfg)
        assert child != cfg.inhalation_m3_per_h["light"]["child"]


# ------------------------------------------------------------------ 7. nowcast and fire


class TestForecastRefinements:
    def test_nowcast_fades_with_lead_time(self, cfg: EngineConfig) -> None:
        t0 = datetime(2026, 10, 3, 6, tzinfo=UTC)
        fc = {t0 + timedelta(hours=h): 100.0 for h in range(0, 49)}
        out = nowcast(fc, t0, latest_ratio=2.0, cfg=cfg)
        assert out[t0] == 100
        assert out[t0 + timedelta(hours=6)] == pytest.approx(100 * 2 ** math.exp(-1))
        assert out[t0 + timedelta(hours=48)] == pytest.approx(100, abs=0.1)

    @pytest.mark.parametrize(
        ("count", "risk"), [(0, "none"), (1, "low"), (25, "medium"), (99, "medium"), (100, "high")]
    )
    def test_fire_risk_levels(self, cfg: EngineConfig, count: int, risk: str) -> None:
        assert fire_risk(count, cfg) == risk

    def test_fire_flag_does_not_change_numbers_until_calibrated(self, cfg: EngineConfig) -> None:
        quiet = forecast(ADULT_MAN, DAY, EXAMPLE_PLAN, EXAMPLE_READINGS, cfg)
        smoky = forecast(ADULT_MAN, DAY, EXAMPLE_PLAN, EXAMPLE_READINGS, cfg, upwind_fires=150)
        assert smoky.fire_risk == "high"
        assert smoky.result == quiet.result


# ------------------------------------------------------------------ 8. uncertainty


def _width(lo: float, hi: float, mid: float) -> float:
    return (hi - lo) / mid


class TestUncertainty:
    def test_same_seed_same_answer(self, cfg: EngineConfig) -> None:
        a = estimate_range(
            ADULT_MAN, DAY, EXAMPLE_PLAN, EXAMPLE_READINGS, cfg, random.Random(7), runs=50
        )
        b = estimate_range(
            ADULT_MAN, DAY, EXAMPLE_PLAN, EXAMPLE_READINGS, cfg, random.Random(7), runs=50
        )
        assert a == b

    def test_range_brackets_the_central_estimate(self, cfg: EngineConfig) -> None:
        u = estimate_range(ADULT_MAN, DAY, EXAMPLE_PLAN, EXAMPLE_READINGS, cfg, random.Random(1))
        assert u.score_p10 < u.score_p50 < u.score_p90
        assert u.score_p50 == pytest.approx(622, rel=0.15)
        assert sum(u.band_probability.values()) == pytest.approx(1)
        assert u.band_probability["red"] > 0.5

    def test_more_known_inputs_give_a_narrower_range(self, cfg: EngineConfig) -> None:
        vague = estimate_range(
            ADULT_MAN, DAY, EXAMPLE_PLAN, EXAMPLE_READINGS, cfg, random.Random(3), runs=400
        )
        detailed_plan = replace(EXAMPLE_PLAN, home_indoor=IndoorState(size="2bhk"))
        detailed = estimate_range(
            replace(ADULT_MAN, weight_kg=70),
            DAY,
            detailed_plan,
            EXAMPLE_READINGS,
            cfg,
            random.Random(3),
            runs=400,
            air_corrected=True,
        )
        assert _width(detailed.score_p10, detailed.score_p90, detailed.score_p50) < _width(
            vague.score_p10, vague.score_p90, vague.score_p50
        )


# ------------------------------------------------------------------ source tips


def test_source_tips_offer_free_actions_when_indoor_sources_dominate(cfg: EngineConfig) -> None:
    from lung.engine.tips import tips

    home = IndoorState(
        sources=(
            SourceUse("cooking_lpg", time(19, 30), 45),
            SourceUse("mosquito_coil", time(22, 0), 480),
        )
    )
    plan = replace(EXAMPLE_PLAN, home_indoor=home, goes_to_office=False)
    result = {t.id: t for t in tips(ADULT_MAN, DAY, plan, EXAMPLE_READINGS, cfg)}
    assert "source_mosquito_coil" in result  # the biggest single fix
    # The only free option here (cooking with the exhaust on) saves ~2 %: below the bar, so
    # it isn't padded in. Nothing offered may be a token gesture, free or not.
    assert all(t.saves_pct >= cfg.tips.min_saving_pct for t in result.values())
    assert "close_windows_home" not in result  # closing windows traps indoor smoke


def test_scaling_a_source_lowers_only_that_source(cfg: EngineConfig) -> None:
    from lung.engine.day import apply_change
    from lung.engine.models import Change

    home = IndoorState(sources=(SourceUse("cooking_lpg", time(19, 30), 45),))
    plan = replace(EXAMPLE_PLAN, home_indoor=home)
    changed = apply_change(plan, Change(scale_sources=(("cooking_lpg", 0.5),)))
    assert changed.home_indoor.sources[0].scale == 0.5
    cooking = next(s for s in build_day(DAY, plan, cfg) if s.added_ugm3 > 0)
    halved = next(s for s in build_day(DAY, changed, cfg) if s.added_ugm3 > 0)
    assert halved.added_ugm3 == pytest.approx(cooking.added_ugm3 / 2)
