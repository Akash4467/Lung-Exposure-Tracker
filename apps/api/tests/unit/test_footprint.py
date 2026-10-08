"""Commute footprint (estimated CO2). Hand-checked against footprint.yaml."""

import pytest

from lung.engine import footprint as fp
from lung.infra.engine_config import load_footprint

CFG = load_footprint()


def test_car_commute_week_and_best_swap() -> None:
    # 10 km each way, 5 days: 100 km a week by car at 0.140 kg/km (0.111-0.213)
    c = fp.commute("car", 10, 5, CFG)
    assert c.week_km == 100
    assert c.week_kg.central == pytest.approx(14.0)
    assert (c.week_kg.low, c.week_kg.high) == (pytest.approx(11.1), pytest.approx(21.3))
    assert c.year_kg.central == pytest.approx(14.0 * 48)
    s = c.suggestion
    assert s is not None and s.days_per_week == 2 and s.clear
    # 40 km by bus instead of car: (0.140 - 0.0152) x 40
    assert s.mode == "bus"
    assert s.week_kg_saved.central == pytest.approx((0.140 - 0.0152) * 40)
    assert s.week_kg_saved.low == pytest.approx((0.111 - 0.0303) * 40)  # pessimistic end


def test_too_far_to_walk_or_cycle_is_not_offered() -> None:
    modes = {m.mode for m in fp.commute("car", 10, 5, CFG).modes}
    assert "walk" not in modes and "cycle" not in modes
    near = fp.commute("car", 1.5, 5, CFG)
    assert {"walk", "cycle"} <= {m.mode for m in near.modes}
    assert near.suggestion is not None and near.suggestion.mode in {"walk", "cycle"}  # zero CO2


def test_metro_is_not_claimed_to_beat_a_scooter() -> None:
    # per km the metro (0.040) is no better than a scooter (0.0368): never suggest it
    s = fp.commute("two_wheeler", 10, 5, CFG).suggestion
    assert s is not None and s.mode == "bus"


def test_unclear_saving_is_flagged() -> None:
    # metro user, too far to cycle: bus saves on average, but the ranges overlap
    s = fp.commute("metro", 12, 5, CFG).suggestion
    assert s is not None and s.mode == "bus" and not s.clear


def test_nothing_to_suggest_for_walkers_and_no_office_days() -> None:
    assert fp.commute("walk", 1, 5, CFG).suggestion is None
    assert fp.commute("car", 10, 0, CFG).suggestion is None


def test_recorded_legs_add_up_by_mode() -> None:
    r = fp.recorded([("car", 10.0), ("car", 5.0), ("walk", 1.0), ("run", 2.0)], CFG)
    assert r.km_by_mode == {"car": 15.0, "walk": 3.0}
    assert r.total_kg.central == pytest.approx(15 * 0.140)


def test_ranges_must_be_ordered() -> None:
    raw = {
        "factors": {"car": {"low": 0.2, "central": 0.1, "high": 0.3}},
        "suggest": {
            "swap_days_per_week": 2,
            "weeks_per_year": 48,
            "max_walk_km": 2,
            "max_cycle_km": 8,
            "candidates": [],
        },
        "sources": {},
    }
    with pytest.raises(ValueError):
        fp.parse_footprint(raw)


def test_low_carbon_commuters_see_what_they_avoid_versus_driving() -> None:
    c = fp.commute("bus", 21.2, 5, CFG)
    assert c.suggestion is None  # nothing beats the bus at 21 km
    assert c.vs_car_week_kg is not None
    assert c.vs_car_week_kg.central == pytest.approx((0.140 - 0.0152) * 212)
    assert c.vs_car_week_kg.low > 0  # clear even at the pessimistic end
    assert fp.commute("car", 10, 5, CFG).vs_car_week_kg is None
