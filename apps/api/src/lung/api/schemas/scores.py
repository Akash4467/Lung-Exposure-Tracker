from datetime import date, datetime
from typing import Annotated, Any, Literal

from pydantic import Field

from lung.api.schemas.common import Model
from lung.repositories.daily_scores import ScoreRow

DISCLAIMER = "Estimated exposure. Informational only, not medical advice."


class Range(Model):
    p10: float
    p90: float


class Split(Model):
    home: float
    commute: float
    office: float


class Tip(Model):
    id: str
    text: str
    saves_pct: float
    free: bool


class HourOut(Model):
    start: datetime
    pm25: float


class ScoreOut(Model):
    date: date
    is_forecast: bool
    score: int
    range: Range
    band: Literal["green", "amber", "red"]
    band_probability: dict[str, float]
    dose_ug: float
    cigarettes: float
    avg_pm25: float
    split: Split
    indoor_source_share: float
    by_activity: dict[str, float] = {}  # share of the dose while asleep / light / walk / run…
    breathing_lpm: float | None = None  # average litres of air per minute
    air_litres: float | None = None  # air breathed over the day
    ref_ug: float | None = None  # the same breathing at the WHO guideline (15 µg/m³)
    sensitivity: float | None = None  # M: >1 for children, 65+ or a lung condition
    times_who: float | None = None  # dose ÷ ref × M = score ÷ 100
    trip: dict[str, Any] | None = None  # {"id", "label"} when this day is spent on a trip
    tips: list[Tip] = []
    hours: list[HourOut] = []
    worst_hours: list[HourOut] = []
    best_outdoor_hours: list[HourOut] = []
    fire_risk: str | None
    data_as_of: datetime
    computed_at: datetime | None
    engine_version: str
    estimated: Literal[True] = True
    disclaimer: str = DISCLAIMER

    @classmethod
    def from_row(cls, r: ScoreRow) -> "ScoreOut":
        d: dict[str, Any] = r.details or {}
        return cls(
            date=r.date,
            is_forecast=r.is_forecast,
            score=round(r.score),
            range=Range(p10=round(r.score_p10), p90=round(r.score_p90)),
            band=r.band,
            band_probability={k: round(v, 2) for k, v in d.get("band_probability", {}).items()},
            dose_ug=round(r.dose_ug, 1),
            cigarettes=round(r.cigarettes, 1),
            avg_pm25=round(r.avg_pm25, 1),
            split=Split(
                home=round(r.home_share, 3),
                commute=round(r.commute_share, 3),
                office=round(r.office_share, 3),
            ),
            indoor_source_share=round(r.indoor_source_share, 3),
            by_activity={k: round(v, 3) for k, v in d.get("by_activity", {}).items()},
            breathing_lpm=round(d["breathing_lpm"], 1) if d.get("breathing_lpm") else None,
            air_litres=round(d["air_m3"] * 1000) if d.get("air_m3") else None,
            ref_ug=round(d["ref_ug"], 1) if d.get("ref_ug") else None,
            sensitivity=d.get("sensitivity"),
            times_who=round(r.score / 100, 1),
            trip=d.get("trip"),
            tips=[Tip(**t) for t in d.get("tips", [])],
            hours=[HourOut(**h) for h in d.get("hours", [])],
            worst_hours=[HourOut(**h) for h in d.get("worst_hours", [])],
            best_outdoor_hours=[HourOut(**h) for h in d.get("best_outdoor_hours", [])],
            fire_risk=r.fire_risk,
            data_as_of=r.data_as_of,
            computed_at=r.computed_at,
            engine_version=r.engine_version,
        )


class SimulateIn(Model):
    commute_shift_minutes: Annotated[int, Field(ge=-180, le=180)] = 0
    mitigations: Annotated[list[str], Field(max_length=10)] = []


class Brief(Model):
    score: int
    band: str
    dose_ug: float
    cigarettes: float


class SimulateOut(Model):
    before: Brief
    after: Brief
    saves_pct: float
    as_workday: bool = False  # today is a day off; the commute change was tried as a workday
    estimated: Literal[True] = True


class DayOut(Model):
    date: date
    score: int
    band: Literal["green", "amber", "red"]
    dose_ug: float
    avg_pm25: float
    breathing_lpm: float | None = None
    by_activity: dict[str, float] = {}

    @classmethod
    def from_row(cls, r: ScoreRow) -> "DayOut":
        d: dict[str, Any] = r.details or {}
        return cls(
            date=r.date,
            score=round(r.score),
            band=r.band,
            dose_ug=round(r.dose_ug, 1),
            avg_pm25=round(r.avg_pm25, 1),
            breathing_lpm=round(d["breathing_lpm"], 1) if d.get("breathing_lpm") else None,
            by_activity={k: round(v, 3) for k, v in d.get("by_activity", {}).items()},
        )


class DayRef(Model):
    date: date
    score: int


class Insights(Model):
    days: int
    avg_score_7d: int | None
    avg_score_prev_7d: int | None
    change_pct: float | None  # this week against last week; negative = better
    bands: dict[str, int]
    worst_day: DayRef | None
    best_day: DayRef | None
    exercise_share: float  # share of the dose breathed while walking, running or cycling
    avg_breathing_lpm: float | None


class HistoryOut(Model):
    days: list[DayOut]
    insights: Insights
    estimated: Literal[True] = True
    disclaimer: str = DISCLAIMER
