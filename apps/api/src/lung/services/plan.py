"""Turns stored rows into engine inputs for one user and one local date."""

from dataclasses import dataclass
from datetime import UTC, date, datetime, time, timedelta
from uuid import UUID
from zoneinfo import ZoneInfo

from sqlalchemy.ext.asyncio import AsyncSession

from lung.domain.geo import LatLon, cell_id, midpoint
from lung.engine.models import (
    ActivityInterval,
    DayPlan,
    IndoorState,
    Profile,
    RoutePoint,
    Schedule,
    SourceUse,
    TravelLeg,
    Visit,
)
from lung.repositories import activity as activity_repo
from lung.repositories import places as places_repo
from lung.repositories import profiles as profiles_repo
from lung.repositories import routes as routes_repo
from lung.repositories import schedules as schedules_repo
from lung.repositories import travel as travel_repo
from lung.repositories import trips as trips_repo
from lung.repositories import visits as visits_repo
from lung.repositories.places import PlaceRow
from lung.repositories.trips import TripRow


class ProfileIncompleteError(LookupError):
    """The user hasn't finished onboarding: no profile, places or schedule yet."""


@dataclass(frozen=True)
class UserInputs:
    profile: Profile
    tz: str
    home: PlaceRow
    office: PlaceRow
    schedule: Schedule
    office_days: tuple[int, ...]
    route: tuple[RoutePoint, ...]
    commute_cell: str
    trips: tuple[TripRow, ...] = ()

    @property
    def cells(self) -> list[str]:
        cells = {self.home.cell_id, self.office.cell_id, self.commute_cell}
        cells.update(p.cell_id for p in self.route)
        return sorted(cells)

    def cells_for(self, *days: date) -> list[str]:
        """The usual cells plus the destination of any trip on these days."""
        cells = set(self.cells)
        cells.update(t.cell_id for t in self.trips if any(t.covers(d) for d in days))
        return sorted(cells)

    def trip_on(self, day: date) -> TripRow | None:
        return next((t for t in self.trips if t.covers(day)), None)

    def plan_for(self, day: date) -> DayPlan:
        trip = self.trip_on(day)
        if trip is not None:
            # Away: a day off at the destination, inside a typical room (normal windows, no
            # purifier, none of the home's own smoke sources). Same sleep and wake times.
            return DayPlan(
                schedule=self.schedule,
                tz=self.tz,
                home_cell=trip.cell_id,
                office_cell=self.office.cell_id,
                commute_cell=self.commute_cell,
                home_indoor=IndoorState(),
                office_indoor=_indoor(self.office),
                goes_to_office=False,
                route=(),
            )
        return DayPlan(
            schedule=self.schedule,
            tz=self.tz,
            home_cell=self.home.cell_id,
            office_cell=self.office.cell_id,
            commute_cell=self.commute_cell,
            home_indoor=_indoor(self.home),
            office_indoor=_indoor(self.office),
            goes_to_office=day.isoweekday() in self.office_days,
            route=self.route,
        )

    def local_day_window(self, day: date) -> tuple[datetime, datetime]:
        """UTC [start, end) covering the local day, with an hour of margin each side."""
        midnight = datetime.combine(day, time(0), tzinfo=ZoneInfo(self.tz))
        return (
            (midnight - timedelta(hours=1)).astimezone(UTC),
            (midnight + timedelta(hours=25)).astimezone(UTC),
        )


def _indoor(p: PlaceRow) -> IndoorState:
    return IndoorState(
        windows=p.windows,  # type: ignore[arg-type]
        purifier=p.purifier,
        purifier_cadr_m3h=p.purifier_cadr_m3h,
        size=p.size,
        sources=tuple(SourceUse(s.kind, s.start_time, s.minutes) for s in p.sources),
    )


async def load_inputs(
    s: AsyncSession, user_id: UUID, resolution_deg: float, now: datetime
) -> UserInputs:
    profile = await profiles_repo.get(s, user_id)
    places = await places_repo.for_user(s, user_id)
    sched = await schedules_repo.get(s, user_id)
    if profile is None or sched is None or "home" not in places or "office" not in places:
        raise ProfileIncompleteError(str(user_id))
    home, office = places["home"], places["office"]
    # the app's clock, not the wall clock: they differ in tests (a fixed day) and must agree
    today = now.astimezone(ZoneInfo(profile.timezone)).date()
    # two days back: covers yesterday in any time zone; covers() checks exact dates
    trips = await trips_repo.ending_from(s, user_id, today - timedelta(days=2))
    route = tuple(RoutePoint(p.cell_id, p.road_class) for p in await routes_repo.points(s, user_id))
    mid = midpoint(LatLon(home.lat, home.lon), LatLon(office.lat, office.lon))
    return UserInputs(
        profile=Profile(
            age=profile.age,
            sex=profile.sex,  # type: ignore[arg-type]
            sensitive=profile.sensitive,
            weight_kg=profile.weight_kg,
        ),
        tz=profile.timezone,
        home=home,
        office=office,
        schedule=Schedule(
            wake=sched.wake,
            leave_home=sched.leave_home,
            arrive_office=sched.arrive_office,
            leave_office=sched.leave_office,
            arrive_home=sched.arrive_home,
            sleep=sched.sleep,
            commute_mode=sched.commute_mode,  # type: ignore[arg-type]
            commute_mask=sched.commute_mask,  # type: ignore[arg-type]
        ),
        office_days=sched.office_days,
        route=route,
        commute_cell=cell_id(mid.lat, mid.lon, resolution_deg),
        trips=tuple(trips),
    )


async def load_travel(
    s: AsyncSession, user_id: UUID, start: datetime, end: datetime
) -> tuple[TravelLeg, ...]:
    rows = await travel_repo.between(s, user_id, start, end)
    return tuple(
        TravelLeg(r.start_at, r.end_at, r.cell_id, r.mode)  # type: ignore[arg-type]
        for r in rows
    )


async def load_activity(
    s: AsyncSession, user_id: UUID, start: datetime, end: datetime
) -> tuple[ActivityInterval, ...]:
    rows = await activity_repo.between(s, user_id, start, end)
    return tuple(
        ActivityInterval(r.start_at, r.end_at, r.kind, r.met, r.outdoors)  # type: ignore[arg-type]
        for r in rows
    )


async def load_visits(
    s: AsyncSession, user_id: UUID, start: datetime, end: datetime
) -> tuple[Visit, ...]:
    rows = await visits_repo.between(s, user_id, start, end)
    return tuple(
        Visit(r.place, r.start_at, r.end_at, r.activity)  # type: ignore[arg-type]
        for r in rows
    )
