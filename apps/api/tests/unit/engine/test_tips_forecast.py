from dataclasses import replace

import pytest

from lung.engine.config import EngineConfig
from lung.engine.forecast import forecast
from lung.engine.models import IndoorState
from lung.engine.tips import tips

from .conftest import ADULT_MAN, DAY, EXAMPLE_PLAN, EXAMPLE_READINGS, hourly


def test_tips_are_ranked_capped_and_include_a_free_action(cfg: EngineConfig) -> None:
    result = tips(ADULT_MAN, DAY, EXAMPLE_PLAN, EXAMPLE_READINGS, cfg)
    assert 1 <= len(result) <= cfg.tips.max_tips
    assert [t.saves_pct for t in result] == sorted((t.saves_pct for t in result), reverse=True)
    assert any(t.free for t in result)
    assert result[0].id == "purifier_home"
    assert result[0].saves_pct == pytest.approx(26.5, abs=0.1)


def test_no_tip_for_what_is_already_done(cfg: EngineConfig) -> None:
    plan = replace(EXAMPLE_PLAN, home_indoor=IndoorState("closed", True))
    ids = {t.id for t in tips(ADULT_MAN, DAY, plan, EXAMPLE_READINGS, cfg)}
    assert "purifier_home" not in ids
    assert "close_windows_home" not in ids


UTC_PLAN = replace(EXAMPLE_PLAN, tz="UTC")  # local hours == reading hours, for readable tests


def test_smallest_commute_shift_that_avoids_rush_hour(cfg: EngineConfig) -> None:
    # Commute air is terrible 08:00-10:00 and 17:00-19:00. Trips are 08:30 and 17:00.
    # -60 (07:30 / 16:00), -120 and +120 all avoid it; +60 (09:30 / 18:00) does not.
    dirty = {8: 400.0, 9: 400.0, 17: 400.0, 18: 400.0}
    readings = {
        "home": hourly(50, offset_minutes=0),
        "office": hourly(50, offset_minutes=0),
        "commute": hourly({h: dirty.get(h, 20.0) for h in range(24)}, offset_minutes=0),
    }
    shift = [t for t in tips(ADULT_MAN, DAY, UTC_PLAN, readings, cfg) if t.id.startswith("shift")]
    assert [t.id for t in shift] == ["shift_commute_-60"]
    assert shift[0].free
    assert shift[0].text == "Leave 1 hour earlier, both ways"


def test_forecast_flags_worst_and_best_hours(cfg: EngineConfig) -> None:
    home = {h: 100.0 for h in range(24)} | {7: 300.0, 8: 280.0, 22: 260.0, 14: 20.0}
    readings = {
        k: hourly(v, offset_minutes=0)
        for k, v in {"home": home, "office": 150.0, "commute": 200.0}.items()
    }
    f = forecast(ADULT_MAN, DAY, UTC_PLAN, readings, cfg)
    assert len(f.hours) == 24
    assert [h.start.hour for h in f.worst_hours] == [7, 8, 22]
    assert f.best_outdoor_hours[0].start.hour == 14
    assert all(6 <= h.start.hour < 21 for h in f.best_outdoor_hours)
    assert f.result.band in {"green", "amber", "red"}


def test_forecast_hours_in_india_blend_the_two_utc_hours(cfg: EngineConfig) -> None:
    # IST is UTC+5:30, so local 07:00-08:00 is half of UTC 01:00 and half of UTC 02:00.
    utc_values = {1: 100.0, 2: 300.0}
    readings = dict(EXAMPLE_READINGS) | {"home": hourly(utc_values, offset_minutes=0)}
    f = forecast(ADULT_MAN, DAY, EXAMPLE_PLAN, readings, cfg)
    assert len(f.hours) == 24
    seven = next(h for h in f.hours if h.start.hour == 7)
    assert seven.pm25 == pytest.approx(200)
    assert seven.start.utcoffset() is not None
