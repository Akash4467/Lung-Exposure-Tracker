from datetime import date, datetime
from typing import Annotated, Literal
from zoneinfo import available_timezones

from pydantic import AwareDatetime, Field, field_validator

from lung.api.schemas.common import HHMM, Model

Windows = Literal["closed", "normal", "open"]
CommuteMode = Literal["walk", "cycle", "bus", "metro", "two_wheeler", "car"]
Mask = Literal["none", "cloth", "surgical", "n95"]
Activity = Literal["asleep", "light", "walk", "run", "cycle"]


class SourceIn(Model):
    kind: Annotated[str, Field(max_length=40, examples=["cooking_lpg"])]
    start: HHMM
    minutes: Annotated[int, Field(ge=1, le=1440)]


class PlaceIn(Model):
    label: Annotated[str | None, Field(max_length=60)] = None
    lat: Annotated[float, Field(ge=-90, le=90)]
    lon: Annotated[float, Field(ge=-180, le=180)]
    windows: Windows = "normal"
    purifier: bool = False
    purifier_cadr_m3h: Annotated[float | None, Field(gt=0, le=2000)] = None
    size: Annotated[str | None, Field(max_length=20, examples=["2bhk"])] = None
    sources: Annotated[list[SourceIn], Field(max_length=20)] = []


class PlacesIn(Model):
    home: PlaceIn
    office: PlaceIn


class ScheduleIn(Model):
    wake: HHMM
    leave_home: HHMM
    arrive_office: HHMM
    leave_office: HHMM
    arrive_home: HHMM
    sleep: HHMM
    commute_mode: CommuteMode
    commute_mask: Mask = "none"
    office_days: Annotated[list[Annotated[int, Field(ge=1, le=7)]], Field(max_length=7)] = [
        1,
        2,
        3,
        4,
        5,
    ]


class ProfileIn(Model):
    age: Annotated[int, Field(ge=3, le=110)]
    sex: Literal["man", "woman", "other"]
    sensitive: bool = False
    weight_kg: Annotated[float | None, Field(ge=10, le=300)] = None
    timezone: str = "Asia/Kolkata"
    places: PlacesIn
    schedule: ScheduleIn

    @field_validator("timezone")
    @classmethod
    def _known_tz(cls, v: str) -> str:
        if v not in available_timezones():
            raise ValueError("unknown time zone")
        return v


class PlaceOut(PlaceIn):
    cell_id: str


class PlacesOut(Model):
    home: PlaceOut
    office: PlaceOut


class ProfileOut(Model):
    age: int
    sex: str
    sensitive: bool
    weight_kg: float | None
    timezone: str
    places: PlacesOut
    schedule: ScheduleIn


class IndoorIn(Model):
    """Change any subset; omitted fields stay as they are. `sources: []` removes all."""

    place: Literal["home", "office"]
    windows: Windows | None = None
    purifier: bool | None = None
    purifier_cadr_m3h: Annotated[float | None, Field(gt=0, le=2000)] = None
    clear_cadr: bool = False
    size: Annotated[str | None, Field(max_length=20)] = None
    sources: Annotated[list[SourceIn] | None, Field(max_length=20)] = None


class VisitIn(Model):
    place: Literal["home", "office", "away"]
    start: AwareDatetime
    end: AwareDatetime
    activity: Activity | None = None


class VisitsIn(Model):
    visits: Annotated[list[VisitIn], Field(max_length=200)]


class DeviceIn(Model):
    fcm_token: Annotated[str, Field(min_length=10, max_length=4096)]
    platform: Literal["android", "ios"]


class ActivityIn(Model):
    """One stretch of measured or logged activity. Send `kind`, or heart rate / steps and the
    server works out the exertion and the kind."""

    start: AwareDatetime
    end: AwareDatetime
    kind: Activity | None = None
    heart_rate: Annotated[float | None, Field(ge=30, le=230)] = None  # average bpm
    resting_hr: Annotated[float | None, Field(ge=30, le=120)] = None  # from the watch
    steps_per_min: Annotated[float | None, Field(ge=0, le=300)] = None
    met: Annotated[float | None, Field(ge=0.5, le=25)] = None
    outdoors: bool | None = None  # None: walking/running at home or work counts as outside
    source: Literal["manual", "activity_recognition", "health_connect"] = "manual"


class ActivitiesIn(Model):
    activities: Annotated[list[ActivityIn], Field(min_length=1, max_length=500)]


class ActivityOut(Model):
    id: int
    start: datetime
    end: datetime
    kind: Activity
    met: float | None
    outdoors: bool | None
    source: str
    heart_rate: float | None
    steps_per_min: float | None


class ActivityDayOut(Model):
    date: date
    activities: list[ActivityOut]
