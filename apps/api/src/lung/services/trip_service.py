"""Trips out of town. On trip days the person's Lung Load uses the destination's air: a day
off there, inside a typical room. Destinations starting soon are fetched straight away."""

from datetime import date, timedelta
from typing import Any
from uuid import UUID
from zoneinfo import ZoneInfo

from lung.domain.errors import InvalidInput, NotFound
from lung.domain.geo import cell_id
from lung.repositories import profiles as profiles_repo
from lung.repositories import trips as trips_repo
from lung.repositories.trips import TripRow
from lung.services import ingest_service, score_service
from lung.services.context import AppContext
from lung.services.ingest_service import fetch_msg
from lung.services.plan import ProfileIncompleteError

MAX_DAYS = 60
MAX_AHEAD = timedelta(days=365)
SOON = timedelta(days=3)


async def _today(ctx: AppContext, user_id: UUID) -> date:
    async with ctx.db.session() as s:
        profile = await profiles_repo.get(s, user_id)
    if profile is None:
        raise NotFound("finish onboarding first", "profile_incomplete")
    return ctx.clock().astimezone(ZoneInfo(profile.timezone)).date()


def trip_json(t: TripRow, today: date) -> dict[str, Any]:
    return {
        "id": t.id,
        "label": t.label,
        "lat": t.lat,
        "lon": t.lon,
        "start_date": t.start_date.isoformat(),
        "end_date": t.end_date.isoformat(),
        "days": (t.end_date - t.start_date).days + 1,
        "status": "now" if t.covers(today) else "upcoming",
    }


async def add(
    ctx: AppContext, user_id: UUID, label: str, lat: float, lon: float, start: date, end: date
) -> dict[str, Any]:
    today = await _today(ctx, user_id)
    if end < start:
        raise InvalidInput("the trip must end on or after the day it starts", "bad_trip")
    if end < today:
        raise InvalidInput("that trip is already over", "bad_trip")
    if (end - start).days + 1 > MAX_DAYS:
        raise InvalidInput(f"a trip can be at most {MAX_DAYS} days", "bad_trip")
    if start > today + MAX_AHEAD:
        raise InvalidInput("trips can be planned up to a year ahead", "bad_trip")
    trip = TripRow(
        label=label.strip()[:80] or "Trip",
        lat=lat,
        lon=lon,
        cell_id=cell_id(lat, lon, ctx.settings.cell_resolution_deg),
        start_date=start,
        end_date=end,
    )
    async with ctx.db.session() as s:
        trip_id = await trips_repo.add(s, user_id, trip)
    if start <= today + SOON:
        await _fetch_now(ctx, trip.cell_id)
        await _recompute(ctx, user_id)
    return trip_json(TripRow(**{**trip.__dict__, "id": trip_id}), today)


async def _fetch_now(ctx: AppContext, cell: str) -> None:
    """Get a destination's air straight away so the app updates at once; if the provider is
    slow or down, leave it to the worker (the rescore then follows when the air lands)."""
    try:
        await ingest_service.fetch(ctx, cell, force=True)
    except Exception:
        await ctx.queue.send(ctx.settings.sqs_ingest_url, fetch_msg(cell) | {"force": True})


async def where_today(ctx: AppContext, user_id: UUID) -> dict[str, Any]:
    """Where today's Lung Load is worked out: home, or the place of a trip on today."""
    today = await _today(ctx, user_id)
    async with ctx.db.session() as s:
        rows = await trips_repo.ending_from(s, user_id, today)
    trip = next((t for t in rows if t.covers(today)), None)
    if trip is None:
        return {"kind": "home"}
    return {"kind": "trip", "trip": trip_json(trip, today)}


async def set_today(
    ctx: AppContext, user_id: UUID, place: tuple[str, float, float] | None
) -> dict[str, Any]:
    """ "I'm at home today" (place None) or "I'm at <place> today".

    Any trip covering today ends: one that started today is removed, an earlier one now ends
    yesterday (its past days stay as they were). A place becomes a one-day trip for today.
    """
    today = await _today(ctx, user_id)
    async with ctx.db.session() as s:
        for t in await trips_repo.ending_from(s, user_id, today):
            if not t.covers(today) or t.id is None:
                continue
            if t.start_date >= today:
                await trips_repo.delete(s, user_id, t.id)
            else:
                await trips_repo.set_end(s, user_id, t.id, today - timedelta(days=1))
    if place is None:
        await _recompute(ctx, user_id)
        return {"kind": "home"}
    label, lat, lon = place
    trip = await add(ctx, user_id, label, lat, lon, today, today)
    return {"kind": "trip", "trip": trip}


async def upcoming(ctx: AppContext, user_id: UUID) -> list[dict[str, Any]]:
    today = await _today(ctx, user_id)
    async with ctx.db.session() as s:
        rows = await trips_repo.ending_from(s, user_id, today)
    return [trip_json(t, today) for t in rows]


async def remove(ctx: AppContext, user_id: UUID, trip_id: int) -> None:
    async with ctx.db.session() as s:
        if not await trips_repo.delete(s, user_id, trip_id):
            raise NotFound("no such trip", "trip_not_found")
    await _recompute(ctx, user_id)


async def _recompute(ctx: AppContext, user_id: UUID) -> None:
    try:
        await score_service.recompute(ctx, user_id)
    except (score_service.NoAirDataError, ProfileIncompleteError):
        await ingest_service.queue_recompute(ctx, user_id)
