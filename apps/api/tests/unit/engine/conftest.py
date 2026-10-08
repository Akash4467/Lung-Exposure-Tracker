from collections.abc import Mapping
from datetime import UTC, date, datetime, time, timedelta

import pytest

from lung.engine.config import EngineConfig
from lung.engine.models import DayPlan, Profile, Schedule
from lung.infra.engine_config import load_config

DAY = date(2026, 10, 3)
TZ = "Asia/Kolkata"


@pytest.fixture
def cfg() -> EngineConfig:
    return load_config()


def hourly(
    value: float | Mapping[int, float], day: date = DAY, offset_minutes: int = 330
) -> dict[datetime, float]:
    """UTC hourly readings covering the local day with a margin either side.

    `value` is a constant, or {hour: pm25} keyed by the local hour (UTC + offset) in which
    each UTC reading hour starts; unspecified hours are 0.
    """
    start = datetime.combine(day, time(0), tzinfo=UTC) - timedelta(hours=12)
    out: dict[datetime, float] = {}
    for i in range(48):
        t = start + timedelta(hours=i)
        if isinstance(value, Mapping):
            out[t] = value.get((t + timedelta(minutes=offset_minutes)).hour, 0.0)
        else:
            out[t] = value
    return out


ADULT_MAN = Profile(age=34, sex="man", sensitive=False)

# Worked example from the design doc: 1 h commute, 8 h office, 7 h asleep, 8 h awake at home.
EXAMPLE_SCHEDULE = Schedule(
    wake=time(7, 0),
    leave_home=time(8, 30),
    arrive_office=time(9, 0),
    leave_office=time(17, 0),
    arrive_home=time(17, 30),
    sleep=time(0, 0),
    commute_mode="metro",
)
EXAMPLE_PLAN = DayPlan(
    schedule=EXAMPLE_SCHEDULE,
    tz=TZ,
    home_cell="home",
    office_cell="office",
    commute_cell="commute",
)
EXAMPLE_READINGS = {"home": hourly(180), "office": hourly(150), "commute": hourly(200)}
