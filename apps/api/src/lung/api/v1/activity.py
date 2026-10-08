from datetime import date
from typing import Annotated

from fastapi import APIRouter, Path, Query, status

from lung.api.deps import Ctx, UserId
from lung.api.schemas.profile import ActivitiesIn, ActivityDayOut, ActivityOut
from lung.services import activity_service
from lung.services.activity_service import ActivityLog

router = APIRouter(prefix="/v1/me/activity", tags=["activity"])


@router.post("", status_code=status.HTTP_201_CREATED)
async def post_activity(body: ActivitiesIn, user_id: UserId, ctx: Ctx) -> dict[str, list[int]]:
    """What the person was doing: a manual log ("ran 30 minutes"), the phone's activity
    recognition, or Health Connect heart rate / steps. Manual logs update today's score at
    once; batches from the phone are applied in the background."""
    ids = await activity_service.add(
        ctx,
        user_id,
        [
            ActivityLog(
                start=a.start,
                end=a.end,
                kind=a.kind,
                met=a.met,
                outdoors=a.outdoors,
                source=a.source,
                heart_rate=a.heart_rate,
                resting_hr=a.resting_hr,
                steps_per_min=a.steps_per_min,
            )
            for a in body.activities
        ],
    )
    return {"ids": ids}


@router.get("")
async def get_activity(
    user_id: UserId, ctx: Ctx, day: Annotated[date | None, Query(alias="date")] = None
) -> ActivityDayOut:
    """Activities on a local day (today by default)."""
    d, rows = await activity_service.for_day(ctx, user_id, day)
    return ActivityDayOut(
        date=d,
        activities=[
            ActivityOut(
                id=r.id or 0,
                start=r.start_at,
                end=r.end_at,
                kind=r.kind,
                met=r.met,
                outdoors=r.outdoors,
                source=r.source,
                heart_rate=r.heart_rate,
                steps_per_min=r.steps_per_min,
            )
            for r in rows
        ],
    )


@router.delete("/{activity_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_activity(
    activity_id: Annotated[int, Path(ge=1)], user_id: UserId, ctx: Ctx
) -> None:
    await activity_service.remove(ctx, user_id, activity_id)
