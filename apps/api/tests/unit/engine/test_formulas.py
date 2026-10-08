from datetime import UTC, datetime

import pytest

from lung.engine.config import EngineConfig
from lung.engine.dose import MissingReadingError, breathing_rate, outdoor_pm25
from lung.engine.indoor import indoor_factor
from lung.engine.models import IndoorState, Profile, Segment
from lung.engine.score import band_for, compute, sensitivity


def _seg(start: datetime, end: datetime, **kw: object) -> Segment:
    base: dict[str, object] = {
        "place": "home",
        "activity": "light",
        "cell_id": "c",
        "factor": 1.0,
    }
    base.update(kw)
    return Segment(start=start, end=end, **base)  # type: ignore[arg-type]


def utc(h: int, m: int = 0) -> datetime:
    return datetime(2026, 10, 3, h, m, tzinfo=UTC)


class TestBreathingRate:
    def test_adult_columns(self, cfg: EngineConfig) -> None:
        assert breathing_rate(Profile(30, "man", False), "walk", cfg) == 1.4
        assert breathing_rate(Profile(30, "woman", False), "walk", cfg) == 1.2

    def test_other_averages_adults(self, cfg: EngineConfig) -> None:
        assert breathing_rate(Profile(30, "other", False), "walk", cfg) == pytest.approx(1.3)

    @pytest.mark.parametrize("age", [3, 11])
    def test_children_use_child_column(self, cfg: EngineConfig, age: int) -> None:
        assert breathing_rate(Profile(age, "man", False), "cycle", cfg) == 1.6

    def test_twelve_is_adult(self, cfg: EngineConfig) -> None:
        assert breathing_rate(Profile(12, "woman", False), "cycle", cfg) == 2.0


class TestSensitivity:
    @pytest.mark.parametrize(
        ("age", "sensitive", "expected"),
        [(30, False, 1.0), (65, False, 1.3), (10, False, 1.5), (30, True, 1.5), (70, True, 1.5)],
    )
    def test_highest_applies_not_product(
        self, cfg: EngineConfig, age: int, sensitive: bool, expected: float
    ) -> None:
        assert sensitivity(Profile(age, "man", sensitive), cfg) == expected


@pytest.mark.parametrize(
    ("score", "band"),
    [(0, "green"), (100, "green"), (100.1, "amber"), (400, "amber"), (401, "red")],
)
def test_bands(cfg: EngineConfig, score: float, band: str) -> None:
    assert band_for(score, cfg) == band


@pytest.mark.parametrize(
    ("state", "expected"),
    [
        (IndoorState("normal", False), 0.5),
        (IndoorState("closed", False), 0.4),
        (IndoorState("open", False), 0.7),
        (IndoorState("normal", True), 0.25),
        (IndoorState("open", True), 0.525),  # a purifier struggles against open windows
        (IndoorState("closed", True), 0.32 / (0.8 + 1.066667)),
    ],
)
def test_indoor_factor(cfg: EngineConfig, state: IndoorState, expected: float) -> None:
    assert indoor_factor(state, cfg) == pytest.approx(expected)


class TestOutdoorPm25:
    def test_time_weighted_across_partial_hours(self) -> None:
        readings = {"c": {utc(8): 100.0, utc(9): 200.0}}
        # 08:30-09:30: half an hour at 100, half at 200
        assert outdoor_pm25(_seg(utc(8, 30), utc(9, 30)), readings) == pytest.approx(150)

    def test_uneven_split(self) -> None:
        readings = {"c": {utc(8): 100.0, utc(9): 200.0}}
        # 08:45-09:30: 15 min at 100, 30 min at 200
        assert outdoor_pm25(_seg(utc(8, 45), utc(9, 30)), readings) == pytest.approx(500 / 3)

    def test_missing_hour_raises(self) -> None:
        with pytest.raises(MissingReadingError) as e:
            outdoor_pm25(_seg(utc(8), utc(10)), {"c": {utc(8): 100.0}})
        assert e.value.hour == utc(9)


def test_mask_and_factor_reduce_dose_not_reference(cfg: EngineConfig) -> None:
    readings = {"c": {utc(8): 100.0}}
    p = Profile(30, "man", False)
    plain = compute(p, [_seg(utc(8), utc(9), activity="walk")], readings, cfg)
    masked = compute(
        p, [_seg(utc(8), utc(9), activity="walk", factor=0.6, mask="n95")], readings, cfg
    )
    assert masked.dose_ug == pytest.approx(plain.dose_ug * 0.6 * 0.3)
    assert masked.ref_ug == plain.ref_ug


def test_clean_air_is_green(cfg: EngineConfig) -> None:
    readings = {"c": {utc(h): 10.0 for h in range(24)}}
    r = compute(Profile(30, "man", False), [_seg(utc(0), utc(23))], readings, cfg)
    assert r.score == pytest.approx(100 * 10 / 15)
    assert r.band == "green"


def test_empty_day_rejected(cfg: EngineConfig) -> None:
    with pytest.raises(ValueError, match="at least one segment"):
        compute(Profile(30, "man", False), [], {}, cfg)
