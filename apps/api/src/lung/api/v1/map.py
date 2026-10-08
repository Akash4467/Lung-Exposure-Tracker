from typing import Annotated, Any

from fastapi import APIRouter, Query
from pydantic import Field

from lung.api.deps import Ctx, UserId
from lung.api.schemas.common import Model
from lung.domain.geo import LatLon
from lung.services import map_service, route_planner

router = APIRouter(prefix="/v1/map", tags=["map"])

Lat = Annotated[float, Query(ge=-90, le=90)]
Lon = Annotated[float, Query(ge=-180, le=180)]


@router.get("/grid")
async def grid(
    user_id: UserId, ctx: Ctx, south: Lat, west: Lon, north: Lat, east: Lon
) -> dict[str, Any]:
    """PM2.5 right now across the visible map area, as up to ~11 x 11 points (coarser when
    zoomed out). Anywhere in the world."""
    return await map_service.grid(ctx, south, west, north, east)


class RouteIn(Model):
    from_lat: Annotated[float, Field(ge=-90, le=90)]
    from_lon: Annotated[float, Field(ge=-180, le=180)]
    to_lat: Annotated[float, Field(ge=-90, le=90)]
    to_lon: Annotated[float, Field(ge=-180, le=180)]


@router.post("/route")
async def route(body: RouteIn, user_id: UserId, ctx: Ctx) -> dict[str, Any]:
    """Plan a trip from A to B by the air: driving (up to 3 alternatives, fastest and
    cleanest marked), cycling and walking routes coloured by roadside PM2.5 now, and each way
    of travelling's dose for the whole trip."""
    return await route_planner.plan(
        ctx, user_id, LatLon(body.from_lat, body.from_lon), LatLon(body.to_lat, body.to_lon)
    )


@router.get("/place")
async def place(user_id: UserId, ctx: Ctx, lat: Lat, lon: Lon) -> dict[str, Any]:
    """Any place: PM2.5 now, hour by hour for yesterday and the next 5 days, and each local
    day's average, peak and cleanest daytime hours (for trips and "what's it like there")."""
    return await map_service.place(ctx, lat, lon)
