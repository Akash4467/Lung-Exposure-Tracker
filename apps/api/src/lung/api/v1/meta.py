from typing import Annotated, Any

from fastapi import APIRouter, Query

from lung.api.deps import Ctx, UserId
from lung.services import air_service, score_service

router = APIRouter(prefix="/v1", tags=["meta"])


@router.get("/catalog")
async def catalog(ctx: Ctx) -> dict[str, Any]:
    """Every option the app can offer (indoor sources, sizes, modes, masks, mitigations).
    Public: the onboarding screens need it before sign-up finishes."""
    return score_service.catalog(ctx)


@router.get("/air")
async def air(
    user_id: UserId,
    ctx: Ctx,
    lat: Annotated[float, Query(ge=-90, le=90)],
    lon: Annotated[float, Query(ge=-180, le=180)],
) -> dict[str, Any]:
    """Hourly PM2.5, PM10 and wind for the grid cell around a point: 24 h back, 48 h ahead."""
    return await air_service.hourly_for_point(ctx, lat, lon)
