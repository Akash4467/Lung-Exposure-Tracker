"""The design doc's worked example. If this fails, the formulas or config.yaml changed."""

import pytest

from lung.engine.config import EngineConfig
from lung.engine.day import build_day
from lung.engine.models import Change
from lung.engine.score import compute
from lung.engine.tips import simulate

from .conftest import ADULT_MAN, DAY, EXAMPLE_PLAN, EXAMPLE_READINGS


def test_worked_example(cfg: EngineConfig) -> None:
    segments = build_day(DAY, EXAMPLE_PLAN, cfg)
    r = compute(ADULT_MAN, segments, EXAMPLE_READINGS, cfg)

    assert r.dose_ug == pytest.approx(1619.5)
    assert r.ref_ug == pytest.approx(260.25)
    assert r.score == pytest.approx(622.3, abs=0.1)
    assert r.band == "red"
    assert r.split["commute"] == pytest.approx(0.173, abs=0.001)
    assert r.split["home"] == pytest.approx(0.531, abs=0.001)
    assert r.split["office"] == pytest.approx(0.296, abs=0.001)
    assert r.avg_pm25 == pytest.approx(89.6, abs=0.1)
    assert r.cigarettes == pytest.approx(4.07, abs=0.01)


def test_worked_example_purifier_saves_about_27_percent(cfg: EngineConfig) -> None:
    sim = simulate(ADULT_MAN, DAY, EXAMPLE_PLAN, Change(purifier_home=True), EXAMPLE_READINGS, cfg)
    assert sim.saves_pct == pytest.approx(26.5, abs=0.1)
    assert sim.after.score == pytest.approx(457, abs=1)
    assert sim.after.band == "red"
