"""Plain data the engine works on. No I/O, no clock, no database types.

Every optional field defaults to "unknown"; the engine then uses a typical value and widens
the uncertainty range. Each detail a user adds makes the estimate more personal and tighter.
"""

from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import datetime, time
from typing import Literal

Sex = Literal["man", "woman", "other"]
Place = Literal["home", "office", "commute"]
Activity = Literal["asleep", "light", "walk", "run", "cycle"]
Band = Literal["green", "amber", "red"]
CommuteMode = Literal["walk", "cycle", "bus_metro", "two_wheeler", "car"]
Windows = Literal["closed", "normal", "open"]
Mask = Literal["none", "cloth", "surgical", "n95"]
FireRisk = Literal["none", "low", "medium", "high"]

PLACES: tuple[Place, ...] = ("home", "office", "commute")

# cell_id -> {UTC hour start -> PM2.5 µg/m³}
Readings = Mapping[str, Mapping[datetime, float]]


@dataclass(frozen=True)
class Profile:
    age: int
    sex: Sex
    sensitive: bool  # self-declared respiratory condition
    weight_kg: float | None = None  # optional: personal breathing rate


@dataclass(frozen=True)
class SourceUse:
    """An indoor PM2.5 source used daily at home, e.g. cooking at 19:30 for 45 minutes.

    `kind` must be a key of `indoor.sources` in config.yaml, so new kinds need no code.
    """

    kind: str
    start: time
    minutes: int
    scale: float = 1.0  # share of the usual emission (a what-if like "use the exhaust" lowers it)


@dataclass(frozen=True)
class IndoorState:
    windows: Windows = "normal"
    purifier: bool = False
    purifier_cadr_m3h: float | None = None  # clean-air delivery rate from the box
    size: str | None = None  # key of indoor.volume_m3, e.g. "2bhk"
    sources: tuple[SourceUse, ...] = ()


@dataclass(frozen=True)
class RoutePoint:
    """One sample along the commute, in travel order from home to office."""

    cell_id: str
    road_class: str = "unknown"  # key of commute.road_factor


@dataclass(frozen=True)
class Schedule:
    """A usual day, in the user's local wall-clock time."""

    wake: time
    leave_home: time
    arrive_office: time
    leave_office: time
    arrive_home: time
    sleep: time
    commute_mode: CommuteMode
    commute_mask: Mask = "none"


@dataclass(frozen=True)
class DayPlan:
    """Everything needed to turn one local date into segments."""

    schedule: Schedule
    tz: str  # IANA name, e.g. "Asia/Kolkata"
    home_cell: str
    office_cell: str
    commute_cell: str  # used when there is no route
    home_indoor: IndoorState = IndoorState()
    office_indoor: IndoorState = IndoorState()
    goes_to_office: bool = True  # False on days off: home all day
    route: tuple[RoutePoint, ...] = ()  # optional: route-aware commute


@dataclass(frozen=True)
class Visit:
    """Observed time in a place, from the phone's geofences and activity recognition.

    "away" means outside both geofences: treated as travel, using the commute air.
    """

    place: Literal["home", "office", "away"]
    start: datetime  # timezone-aware
    end: datetime
    activity: Activity | None = None  # from activity recognition, if known


TravelMode = Literal["walk", "run", "cycle", "bus_metro", "two_wheeler", "car"]


@dataclass(frozen=True)
class TravelLeg:
    """A stretch of travel recorded by the phone (opt-in route recording): when, how, and the
    grid cell it went through. Replaces the schedule's guess for those minutes, with that
    cell's air instead of the declared route."""

    start: datetime  # timezone-aware
    end: datetime
    cell_id: str
    mode: TravelMode


@dataclass(frozen=True)
class ActivityInterval:
    """What the person was actually doing, from the phone (activity recognition, steps),
    a wearable (heart rate) or a manual log. Overrides the schedule's guess for those minutes.

    `met` is the measured exertion if known (from heart rate or cadence); otherwise the
    activity's typical MET from config is used. `outdoors` None means "work it out": moving
    (walk/run/cycle) while at home or work is taken as outdoors nearby.
    """

    start: datetime  # timezone-aware
    end: datetime
    kind: Activity
    met: float | None = None
    outdoors: bool | None = None


@dataclass(frozen=True)
class Segment:
    """One stretch of time in one place doing one thing."""

    place: Place
    activity: Activity
    start: datetime  # timezone-aware
    end: datetime
    cell_id: str  # which grid cell's air applies
    factor: float  # share of outdoor PM2.5 present: 1.0 outdoors, <1 indoors or in a car
    mask: Mask = "none"
    added_ugm3: float = 0.0  # PM2.5 from indoor sources running during this segment
    observed: bool = False  # True when it comes from geofence data, not the schedule
    met: float | None = None  # measured exertion; None = the activity's typical value

    @property
    def hours(self) -> float:
        return (self.end - self.start).total_seconds() / 3600


@dataclass(frozen=True)
class Result:
    dose_ug: float
    ref_ug: float
    score: float
    band: Band
    cigarettes: float
    avg_pm25: float  # 24 h time-weighted concentration actually breathed
    split: dict[Place, float] = field(default_factory=dict)  # share of dose; sums to 1
    indoor_source_share: float = 0.0  # share of dose from indoor sources (cooking, …)
    by_activity: dict[Activity, float] = field(default_factory=dict)  # share of dose; sums to 1
    air_m3: float = 0.0  # air breathed over the segments
    hours: float = 0.0  # time the segments cover

    @property
    def breathing_lpm(self) -> float:
        """Average breathing rate, litres of air per minute."""
        return self.air_m3 * 1000 / (self.hours * 60) if self.hours > 0 else 0.0


@dataclass(frozen=True)
class Change:
    """A what-if: applied to a DayPlan before re-running compute."""

    commute_shift_minutes: int = 0
    purifier_home: bool = False
    purifier_office: bool = False
    close_windows_home: bool = False
    commute_mask: Mask | None = None
    scale_sources: tuple[tuple[str, float], ...] = ()  # (kind, share of emission left)
