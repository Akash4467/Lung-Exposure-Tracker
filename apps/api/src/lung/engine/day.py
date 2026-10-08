"""Turns a schedule (and, when available, observed geofence visits) into the day's segments.

The day is painted minute by minute on the local wall clock:

1. the declared schedule: home-awake, then sleep, then trips and office on top;
2. observed visits overwrite the minutes they cover, but only before `now`;
3. recorded travel legs (opt-in route recording) overwrite those minutes with travel through
   the leg's own cell, with its way of travelling;
4. measured activity (running, walking, heart-rate exertion) overwrites what the person was
   doing, and moving near home or work counts as being outdoors there;
5. indoor sources (cooking, incense, …) are painted on a separate layer.

Minutes with the same (place, activity, exertion, outdoors, sources, observed) merge into one
segment.
Commute segments are then split along the route when one is known.
"""

from collections.abc import Sequence
from dataclasses import replace
from datetime import date, datetime, time, timedelta
from itertools import pairwise
from typing import NamedTuple
from zoneinfo import ZoneInfo

from lung.engine.config import EngineConfig
from lung.engine.indoor import indoor_factor, source_added_ugm3
from lung.engine.models import (
    Activity,
    ActivityInterval,
    Change,
    DayPlan,
    Mask,
    Place,
    RoutePoint,
    Schedule,
    Segment,
    TravelLeg,
    Visit,
)

MINUTES_PER_DAY = 24 * 60
NO_SOURCES: frozenset[str] = frozenset()


class _Label(NamedTuple):
    place: Place
    activity: Activity


class _Run(NamedTuple):
    label: _Label
    sources: frozenset[str]
    observed: bool
    met: float | None
    outdoors: bool  # at home/work but outside (e.g. a run around the block)
    start: int  # minute of day
    end: int
    leg: int | None = None  # index into the recorded travel legs, when this is one


class _Act(NamedTuple):
    met: float | None
    outdoors: bool


NO_ACT = _Act(None, False)
MOVING: frozenset[Activity] = frozenset({"walk", "run", "cycle"})


HOME_AWAKE = _Label("home", "light")
HOME_ASLEEP = _Label("home", "asleep")
OFFICE = _Label("office", "light")


def _m(t: time) -> int:
    return t.hour * 60 + t.minute


def _spans(start: int, end: int) -> list[tuple[int, int]]:
    """[start, end) on a 24 h clock as plain ranges; end <= start wraps past midnight."""
    if end > start:
        return [(start, end)]
    if end < start:
        return [(start, MINUTES_PER_DAY), (0, end)]
    return []


def _paint(day: list[_Label], start: int, end: int, label: _Label) -> None:
    for a, b in _spans(start, end):
        day[a:b] = [label] * (b - a)


def validate_schedule(s: Schedule) -> None:
    """Trips must run in order within the day: leave < arrive < leave < arrive."""
    order = [s.leave_home, s.arrive_office, s.leave_office, s.arrive_home]
    if not all(_m(a) < _m(b) for a, b in pairwise(order)):
        raise ValueError(
            "schedule must satisfy leave_home < arrive_office < leave_office < arrive_home"
        )
    if s.wake == s.sleep:
        raise ValueError("wake and sleep times must differ")


def _declared(plan: DayPlan, cfg: EngineConfig) -> list[_Label]:
    s = plan.schedule
    day = [HOME_AWAKE] * MINUTES_PER_DAY
    _paint(day, _m(s.sleep), _m(s.wake), HOME_ASLEEP)
    if plan.goes_to_office:
        commute = _Label("commute", cfg.commute_activity[s.commute_mode])
        _paint(day, _m(s.leave_home), _m(s.arrive_office), commute)
        _paint(day, _m(s.arrive_office), _m(s.leave_office), OFFICE)
        _paint(day, _m(s.leave_office), _m(s.arrive_home), commute)
    return day


def _overlay_visits(
    day: list[_Label],
    observed: list[bool],
    visits: Sequence[Visit],
    midnight: datetime,
    now: datetime | None,
    plan: DayPlan,
    cfg: EngineConfig,
) -> None:
    """Replace declared minutes with what the phone saw, for minutes already past."""
    limit = MINUTES_PER_DAY
    if now is not None:
        limit = max(0, min(MINUTES_PER_DAY, int((now - midnight).total_seconds() // 60)))
    travel = cfg.commute_activity[plan.schedule.commute_mode]
    for v in visits:
        a = max(0, int((v.start - midnight).total_seconds() // 60))
        b = min(limit, int((v.end - midnight).total_seconds() // 60))
        for minute in range(a, b):
            if v.place == "home":
                asleep = day[minute] == HOME_ASLEEP and v.activity is None
                day[minute] = HOME_ASLEEP if asleep else _Label("home", v.activity or "light")
            elif v.place == "office":
                day[minute] = _Label("office", v.activity or "light")
            else:
                day[minute] = _Label("commute", v.activity or travel)
            observed[minute] = True


def _minute_range(start: datetime, end: datetime, midnight: datetime, limit: int) -> range:
    a = max(0, int((start - midnight).total_seconds() // 60))
    b = min(limit, int((end - midnight).total_seconds() // 60))
    return range(a, max(a, b))


def _overlay_activity(
    day: list[_Label],
    observed: list[bool],
    acts: list[_Act],
    intervals: Sequence[ActivityInterval],
    midnight: datetime,
    now: datetime | None,
) -> None:
    """What the person was measured doing replaces the schedule's guess for those minutes."""
    limit = MINUTES_PER_DAY
    if now is not None:
        limit = max(0, min(MINUTES_PER_DAY, int((now - midnight).total_seconds() // 60)))
    for iv in intervals:
        for minute in _minute_range(iv.start, iv.end, midnight, limit):
            place = day[minute].place
            outdoors = (
                iv.outdoors
                if iv.outdoors is not None
                else iv.kind in MOVING and place in ("home", "office")
            )
            day[minute] = _Label(place, iv.kind)
            acts[minute] = _Act(iv.met, bool(outdoors) and place != "commute")
            observed[minute] = True


def _overlay_travel(
    day: list[_Label],
    observed: list[bool],
    legs_at: list[int | None],
    legs: Sequence[TravelLeg],
    midnight: datetime,
    now: datetime | None,
    cfg: EngineConfig,
) -> None:
    """Recorded travel replaces the guess for those minutes (only the past)."""
    limit = MINUTES_PER_DAY
    if now is not None:
        limit = max(0, min(MINUTES_PER_DAY, int((now - midnight).total_seconds() // 60)))
    for i, leg in enumerate(legs):
        activity = travel_activity(leg.mode, cfg)
        for minute in _minute_range(leg.start, leg.end, midnight, limit):
            day[minute] = _Label("commute", activity)
            observed[minute] = True
            legs_at[minute] = i


def travel_activity(mode: str, cfg: EngineConfig) -> Activity:
    if mode in ("walk", "run", "cycle"):
        return mode  # type: ignore[return-value]
    return cfg.commute_activity[mode]  # type: ignore[index]


def travel_factor(mode: str, cfg: EngineConfig) -> float:
    """Share of outdoor air reaching the person: 1 on foot or bike, the vehicle's factor."""
    return 1.0 if mode in ("walk", "run", "cycle") else cfg.commute_factor[mode]  # type: ignore[index]


def _sources_layer(plan: DayPlan, cfg: EngineConfig) -> list[frozenset[str]]:
    layer = [NO_SOURCES] * MINUTES_PER_DAY
    for use in plan.home_indoor.sources:
        if use.kind not in cfg.indoor.sources:
            raise ValueError(f"unknown indoor source {use.kind!r}")
        start = _m(use.start)
        for a, b in _spans(start, (start + use.minutes) % MINUTES_PER_DAY):
            for minute in range(a, b):
                layer[minute] = layer[minute] | {use.kind}
    return layer


def _runs(
    day: list[_Label],
    sources: list[frozenset[str]],
    observed: list[bool],
    acts: list[_Act],
    legs_at: list[int | None],
) -> list[_Run]:
    # Indoor sources only matter while the person is inside at home.
    keys = [
        (
            day[m],
            sources[m] if day[m].place == "home" and not acts[m].outdoors else NO_SOURCES,
            observed[m],
            acts[m],
            legs_at[m],
        )
        for m in range(MINUTES_PER_DAY)
    ]
    runs: list[_Run] = []
    start = 0
    for minute in range(1, MINUTES_PER_DAY + 1):
        if minute == MINUTES_PER_DAY or keys[minute] != keys[start]:
            label, src, obs, act, leg = keys[start]
            runs.append(_Run(label, src, obs, act.met, act.outdoors, start, minute, leg))
            start = minute
    return runs


def _trip_route(runs: list[_Run], i: int, plan: DayPlan) -> tuple[RoutePoint, ...] | None:
    """The route in travel order for commute run i, or None if it isn't a home-office trip."""
    prev = next((r.label.place for r in reversed(runs[:i]) if r.label.place != "commute"), None)
    nxt = next((r.label.place for r in runs[i + 1 :] if r.label.place != "commute"), None)
    ends = {prev, nxt}
    if ends == {"home", "office"} or (None in ends and ends & {"home", "office"}):
        outbound = nxt == "office" or (nxt is None and prev == "home")
        if plan.route:
            return plan.route if outbound else tuple(reversed(plan.route))
        return (RoutePoint(plan.commute_cell),)
    if ends == {"home"}:  # an errand from home and back: use the home cell's air
        return (RoutePoint(plan.home_cell),)
    return (RoutePoint(plan.commute_cell),)


def build_day(
    local_date: date,
    plan: DayPlan,
    cfg: EngineConfig,
    *,
    visits: Sequence[Visit] = (),
    activity: Sequence[ActivityInterval] = (),
    travel: Sequence[TravelLeg] = (),
    now: datetime | None = None,
) -> list[Segment]:
    s = plan.schedule
    validate_schedule(s)
    midnight = datetime.combine(local_date, time(0), tzinfo=ZoneInfo(plan.tz))

    day = _declared(plan, cfg)
    observed = [False] * MINUTES_PER_DAY
    if visits:
        _overlay_visits(day, observed, visits, midnight, now, plan, cfg)
    legs_at: list[int | None] = [None] * MINUTES_PER_DAY
    if travel:
        _overlay_travel(day, observed, legs_at, travel, midnight, now, cfg)
    acts = [NO_ACT] * MINUTES_PER_DAY
    if activity:
        _overlay_activity(day, observed, acts, activity, midnight, now)
    sources = _sources_layer(plan, cfg)
    runs = _runs(day, sources, observed, acts, legs_at)

    scales = {u.kind: u.scale for u in plan.home_indoor.sources}
    home_f = indoor_factor(plan.home_indoor, cfg, "home")
    office_f = indoor_factor(plan.office_indoor, cfg, "office")
    mode_f = cfg.commute_factor[s.commute_mode]

    segments: list[Segment] = []
    for i, run in enumerate(runs):
        start = midnight + timedelta(minutes=run.start)
        end = midnight + timedelta(minutes=run.end)
        place = run.label.place
        if place == "home":
            added = source_added_ugm3(run.sources, plan.home_indoor, cfg, "home", scales)
            segments.append(
                Segment(
                    "home",
                    run.label.activity,
                    start,
                    end,
                    plan.home_cell,
                    1.0 if run.outdoors else home_f,  # outside near home: outdoor air
                    added_ugm3=added,
                    observed=run.observed,
                    met=run.met,
                )
            )
        elif place == "office":
            segments.append(
                Segment(
                    "office",
                    run.label.activity,
                    start,
                    end,
                    plan.office_cell,
                    1.0 if run.outdoors else office_f,
                    observed=run.observed,
                    met=run.met,
                )
            )
        elif run.leg is not None:
            leg = travel[run.leg]
            segments.append(
                Segment(
                    "commute",
                    run.label.activity,
                    start,
                    end,
                    leg.cell_id,
                    travel_factor(leg.mode, cfg),
                    mask=s.commute_mask,
                    observed=True,
                    met=run.met,
                )
            )
        else:
            segments.extend(
                _commute_segments(
                    run, start, end, _trip_route(runs, i, plan), mode_f, s.commute_mask, cfg
                )
            )
    return segments


def _commute_segments(
    run: _Run,
    start: datetime,
    end: datetime,
    route: tuple[RoutePoint, ...] | None,
    mode_factor: float,
    mask: Mask,
    cfg: EngineConfig,
) -> list[Segment]:
    points = route or ()
    # On foot or by bike the person is in outdoor air whatever their usual mode is.
    base = 1.0 if run.label.activity in MOVING and run.observed else mode_factor
    step = (end - start) / len(points)
    out: list[Segment] = []
    for n, p in enumerate(points):
        road = cfg.road_factor.get(p.road_class, cfg.road_factor["unknown"])
        out.append(
            Segment(
                "commute",
                run.label.activity,
                start + step * n,
                start + step * (n + 1),
                p.cell_id,
                base * road,
                mask=mask,
                observed=run.observed,
                met=run.met,
            )
        )
    return out


def _shift(t: time, minutes: int) -> time:
    total = (_m(t) + minutes) % MINUTES_PER_DAY
    return time(total // 60, total % 60)


def apply_change(plan: DayPlan, change: Change) -> DayPlan:
    """The plan as it would be with one what-if applied."""
    s = plan.schedule
    if change.commute_shift_minutes:
        d = change.commute_shift_minutes
        s = replace(
            s,
            leave_home=_shift(s.leave_home, d),
            arrive_office=_shift(s.arrive_office, d),
            leave_office=_shift(s.leave_office, d),
            arrive_home=_shift(s.arrive_home, d),
        )
    if change.commute_mask is not None:
        s = replace(s, commute_mask=change.commute_mask)

    home, office = plan.home_indoor, plan.office_indoor
    if change.close_windows_home:
        home = replace(home, windows="closed")
    if change.purifier_home:
        home = replace(home, purifier=True)
    if change.purifier_office:
        office = replace(office, purifier=True)
    if change.scale_sources:
        factor = dict(change.scale_sources)
        home = replace(
            home,
            sources=tuple(
                replace(u, scale=u.scale * factor[u.kind]) if u.kind in factor else u
                for u in home.sources
            ),
        )
    return replace(plan, schedule=s, home_indoor=home, office_indoor=office)


def is_noop(plan: DayPlan, change: Change) -> bool:
    return apply_change(plan, change) == plan
