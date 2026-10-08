from datetime import date
from typing import Annotated, Any, Literal

from fastapi import APIRouter, Path, status
from pydantic import Field

from lung.api.deps import Ctx, UserId
from lung.api.schemas.common import Model
from lung.domain.errors import InvalidInput
from lung.services import trip_service

router = APIRouter(prefix="/v1/me", tags=["trips"])


class TripIn(Model):
    label: Annotated[str, Field(min_length=1, max_length=80, examples=["Goa"])]
    lat: Annotated[float, Field(ge=-90, le=90)]
    lon: Annotated[float, Field(ge=-180, le=180)]
    start_date: date
    end_date: date  # inclusive


class LocationIn(Model):
    """Where you are today: `home`, or a place (label + coordinates)."""

    kind: Literal["home", "place"]
    label: Annotated[str | None, Field(max_length=80)] = None
    lat: Annotated[float | None, Field(ge=-90, le=90)] = None
    lon: Annotated[float | None, Field(ge=-180, le=180)] = None


@router.get("/location")
async def get_location(user_id: UserId, ctx: Ctx) -> dict[str, Any]:
    """Where today's Lung Load is worked out: home, or today's trip."""
    return await trip_service.where_today(ctx, user_id)


@router.post("/location")
async def post_location(body: LocationIn, user_id: UserId, ctx: Ctx) -> dict[str, Any]:
    """Change where you are today. A place counts as a one-day trip; home ends any trip on
    today. Today's Lung Load is rescored straight away."""
    if body.kind == "home":
        return await trip_service.set_today(ctx, user_id, None)
    if body.lat is None or body.lon is None:
        raise InvalidInput("a place needs lat and lon", "bad_location")
    return await trip_service.set_today(
        ctx, user_id, ((body.label or "Here").strip() or "Here", body.lat, body.lon)
    )


@router.post("/trips", status_code=status.HTTP_201_CREATED)
async def post_trip(body: TripIn, user_id: UserId, ctx: Ctx) -> dict[str, Any]:
    """A trip out of town. On those days the Lung Load uses the destination's air."""
    return await trip_service.add(
        ctx, user_id, body.label, body.lat, body.lon, body.start_date, body.end_date
    )


@router.get("/trips")
async def get_trips(user_id: UserId, ctx: Ctx) -> dict[str, list[dict[str, Any]]]:
    """Trips that are on now or still to come, soonest first."""
    return {"trips": await trip_service.upcoming(ctx, user_id)}


@router.delete("/trips/{trip_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_trip(trip_id: Annotated[int, Path(ge=1)], user_id: UserId, ctx: Ctx) -> None:
    await trip_service.remove(ctx, user_id, trip_id)
