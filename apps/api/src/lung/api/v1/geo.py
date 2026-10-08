from typing import Annotated, Any

from fastapi import APIRouter, Query

from lung.api.deps import Ctx, UserId
from lung.services import geo_service

router = APIRouter(prefix="/v1/geo", tags=["geo"])

Lat = Annotated[float | None, Query(ge=-90, le=90)]
Lon = Annotated[float | None, Query(ge=-180, le=180)]


@router.get("/search")
async def search(
    user_id: UserId,
    ctx: Ctx,
    q: Annotated[str, Query(max_length=120)],
    lat: Lat = None,
    lon: Lon = None,
) -> dict[str, list[dict[str, Any]]]:
    """Find places by name anywhere in the world (OpenStreetMap). `lat`/`lon` prefer results
    near the person. Cached, so repeated searches are instant."""
    near = (lat, lon) if lat is not None and lon is not None else None
    return {"places": await geo_service.search(ctx, q, near)}


@router.get("/reverse")
async def reverse(
    user_id: UserId,
    ctx: Ctx,
    lat: Annotated[float, Query(ge=-90, le=90)],
    lon: Annotated[float, Query(ge=-180, le=180)],
) -> dict[str, Any]:
    """The name of the place at a point (a map tap, "my location")."""
    return {"place": await geo_service.reverse(ctx, lat, lon)}
