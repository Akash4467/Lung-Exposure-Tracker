from dataclasses import replace
from datetime import time

import pytest

from lung.engine.config import EngineConfig
from lung.engine.day import apply_change, build_day
from lung.engine.models import Change, Segment

from .conftest import DAY, EXAMPLE_PLAN, EXAMPLE_SCHEDULE


def _shape(segs: list[Segment]) -> list[tuple[str, str, str, str]]:
    return [(s.place, s.activity, s.start.strftime("%H:%M"), s.end.strftime("%H:%M")) for s in segs]


def _total_hours(segs: list[Segment]) -> float:
    return sum(s.hours for s in segs)


def test_example_day_shape(cfg: EngineConfig) -> None:
    segs = build_day(DAY, EXAMPLE_PLAN, cfg)
    assert _shape(segs) == [
        ("home", "asleep", "00:00", "07:00"),
        ("home", "light", "07:00", "08:30"),
        ("commute", "walk", "08:30", "09:00"),
        ("office", "light", "09:00", "17:00"),
        ("commute", "walk", "17:00", "17:30"),
        ("home", "light", "17:30", "00:00"),
    ]
    assert _total_hours(segs) == 24
    assert segs[0].start.utcoffset() is not None


def test_sleep_past_midnight_wraps(cfg: EngineConfig) -> None:
    plan = replace(EXAMPLE_PLAN, schedule=replace(EXAMPLE_SCHEDULE, sleep=time(23, 0)))
    segs = build_day(DAY, plan, cfg)
    assert _shape(segs)[0] == ("home", "asleep", "00:00", "07:00")
    assert _shape(segs)[-1] == ("home", "asleep", "23:00", "00:00")
    assert _total_hours(segs) == 24


def test_late_sleeper(cfg: EngineConfig) -> None:
    plan = replace(EXAMPLE_PLAN, schedule=replace(EXAMPLE_SCHEDULE, sleep=time(1, 0)))
    segs = build_day(DAY, plan, cfg)
    assert _shape(segs)[:2] == [
        ("home", "light", "00:00", "01:00"),
        ("home", "asleep", "01:00", "07:00"),
    ]


def test_day_off_is_all_home(cfg: EngineConfig) -> None:
    segs = build_day(DAY, replace(EXAMPLE_PLAN, goes_to_office=False), cfg)
    assert {s.place for s in segs} == {"home"}
    assert _total_hours(segs) == 24


def test_car_commute_uses_cabin_factor_and_light_activity(cfg: EngineConfig) -> None:
    plan = replace(EXAMPLE_PLAN, schedule=replace(EXAMPLE_SCHEDULE, commute_mode="car"))
    commute = [s for s in build_day(DAY, plan, cfg) if s.place == "commute"]
    assert {(s.activity, s.factor) for s in commute} == {("light", 0.6)}


def test_commute_mask_applies_only_to_commute(cfg: EngineConfig) -> None:
    plan = replace(EXAMPLE_PLAN, schedule=replace(EXAMPLE_SCHEDULE, commute_mask="n95"))
    for s in build_day(DAY, plan, cfg):
        assert s.mask == ("n95" if s.place == "commute" else "none")


def test_out_of_order_schedule_rejected(cfg: EngineConfig) -> None:
    bad = replace(EXAMPLE_SCHEDULE, arrive_office=time(8, 0))
    with pytest.raises(ValueError, match="leave_home < arrive_office"):
        build_day(DAY, replace(EXAMPLE_PLAN, schedule=bad), cfg)


def test_shift_moves_all_four_trip_times(cfg: EngineConfig) -> None:
    s = apply_change(EXAMPLE_PLAN, Change(commute_shift_minutes=90)).schedule
    assert (s.leave_home, s.arrive_office, s.leave_office, s.arrive_home) == (
        time(10, 0),
        time(10, 30),
        time(18, 30),
        time(19, 0),
    )
    assert s.wake == EXAMPLE_SCHEDULE.wake


def test_shift_past_midnight_is_rejected(cfg: EngineConfig) -> None:
    plan = apply_change(EXAMPLE_PLAN, Change(commute_shift_minutes=7 * 60))
    with pytest.raises(ValueError):
        build_day(DAY, plan, cfg)
