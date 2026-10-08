from datetime import date
from typing import Annotated, Any, Literal

from fastapi import APIRouter, Query, status
from pydantic import AwareDatetime, Field

from lung.api.deps import Ctx, UserId
from lung.api.schemas.common import Model
from lung.services import track_service
from lung.services.track_service import GpsPoint

router = APIRouter(prefix="/v1/me/tracks", tags=["tracks"])

Confidence = Literal["low", "medium", "high"]


class PointIn(Model):
    t: AwareDatetime
    lat: Annotated[float, Field(ge=-90, le=90)]
    lon: Annotated[float, Field(ge=-180, le=180)]
    speed: Annotated[float | None, Field(ge=0, le=120)] = None  # m/s
    accuracy: Annotated[float | None, Field(ge=0, le=10_000)] = None  # metres
    activity: Literal["walking", "running", "cycling", "automotive", "stationary"] | None = None
    confidence: Confidence | None = None


class TrackIn(Model):
    points: Annotated[list[PointIn], Field(min_length=1, max_length=2000)]


@router.post("", status_code=status.HTTP_202_ACCEPTED)
async def post_track(body: TrackIn, user_id: UserId, ctx: Ctx) -> dict[str, Any]:
    """GPS points from opt-in route recording. Turned into travel legs on arrival; the raw
    points are not stored. Today's Lung Load is rescored in the background."""
    pts = [
        GpsPoint(
            t=p.t,
            lat=p.lat,
            lon=p.lon,
            speed=p.speed,
            accuracy=p.accuracy,
            activity=p.activity,
            confident=p.confidence in ("medium", "high"),
        )
        for p in body.points
    ]
    return await track_service.add_points(ctx, user_id, pts)


@router.get("")
async def get_tracks(
    user_id: UserId, ctx: Ctx, day: Annotated[date | None, Query(alias="date")] = None
) -> dict[str, Any]:
    """Recorded travel legs on a local day (today by default), for the map."""
    return await track_service.legs_for_day(ctx, user_id, day)


@router.delete("", status_code=status.HTTP_200_OK)
async def delete_tracks(user_id: UserId, ctx: Ctx) -> dict[str, int]:
    """Delete everything recorded. Cannot be undone."""
    return {"deleted": await track_service.delete_all(ctx, user_id)}
