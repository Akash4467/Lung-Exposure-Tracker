from typing import Annotated, Any

from fastapi import APIRouter, Path, status

from lung.api.deps import Ctx, UserId
from lung.api.schemas.profile import (
    DeviceIn,
    IndoorIn,
    PlaceIn,
    PlaceOut,
    PlacesOut,
    ProfileIn,
    ProfileOut,
    ScheduleIn,
    SourceIn,
    VisitsIn,
)
from lung.repositories.places import PlaceRow, SourceRow
from lung.repositories.profiles import ProfileRow
from lung.repositories.schedules import ScheduleRow
from lung.repositories.visits import VisitRow
from lung.services import commute_service, footprint_service, profile_service
from lung.services.profile_service import FullProfile, IndoorUpdate

router = APIRouter(prefix="/v1/me", tags=["me"])


def _sources(items: list[SourceIn]) -> tuple[SourceRow, ...]:
    return tuple(SourceRow(s.kind, s.start, s.minutes) for s in items)


def _place_row(kind: str, p: PlaceIn) -> PlaceRow:
    return PlaceRow(
        type=kind,
        label=p.label,
        lat=p.lat,
        lon=p.lon,
        cell_id="",  # set by the service
        windows=p.windows,
        purifier=p.purifier,
        purifier_cadr_m3h=p.purifier_cadr_m3h,
        size=p.size,
        sources=_sources(p.sources),
    )


def _place_out(p: PlaceRow) -> PlaceOut:
    return PlaceOut(
        label=p.label,
        lat=p.lat,
        lon=p.lon,
        windows=p.windows,
        purifier=p.purifier,
        purifier_cadr_m3h=p.purifier_cadr_m3h,
        size=p.size,
        sources=[SourceIn(kind=s.kind, start=s.start_time, minutes=s.minutes) for s in p.sources],
        cell_id=p.cell_id,
    )


def _profile_out(f: FullProfile) -> ProfileOut:
    sc = f.schedule
    return ProfileOut(
        age=f.profile.age,
        sex=f.profile.sex,
        sensitive=f.profile.sensitive,
        weight_kg=f.profile.weight_kg,
        timezone=f.profile.timezone,
        places=PlacesOut(home=_place_out(f.home), office=_place_out(f.office)),
        schedule=ScheduleIn(
            wake=sc.wake,
            leave_home=sc.leave_home,
            arrive_office=sc.arrive_office,
            leave_office=sc.leave_office,
            arrive_home=sc.arrive_home,
            sleep=sc.sleep,
            commute_mode=sc.commute_mode,
            commute_mask=sc.commute_mask,
            office_days=list(sc.office_days),
        ),
    )


@router.get("/profile")
async def get_profile(user_id: UserId, ctx: Ctx) -> ProfileOut:
    return _profile_out(await profile_service.get_profile(ctx, user_id))


@router.put("/profile")
async def put_profile(body: ProfileIn, user_id: UserId, ctx: Ctx) -> ProfileOut:
    """Create or replace the whole profile (onboarding sends everything at once)."""
    sc = body.schedule
    saved = await profile_service.save_profile(
        ctx,
        user_id,
        ProfileRow(user_id, body.age, body.sex, body.sensitive, body.weight_kg, body.timezone),
        _place_row("home", body.places.home),
        _place_row("office", body.places.office),
        ScheduleRow(
            sc.wake,
            sc.leave_home,
            sc.arrive_office,
            sc.leave_office,
            sc.arrive_home,
            sc.sleep,
            sc.commute_mode,
            sc.commute_mask,
            tuple(sorted(set(sc.office_days))),
        ),
    )
    return _profile_out(saved)


@router.put("/indoor")
async def put_indoor(body: IndoorIn, user_id: UserId, ctx: Ctx) -> PlaceOut:
    """Windows, purifier, home size and indoor sources for home or office."""
    place = await profile_service.update_indoor(
        ctx,
        user_id,
        body.place,
        IndoorUpdate(
            windows=body.windows,
            purifier=body.purifier,
            purifier_cadr_m3h=body.purifier_cadr_m3h,
            clear_cadr=body.clear_cadr,
            size=body.size,
            sources=None if body.sources is None else _sources(body.sources),
        ),
    )
    return _place_out(place)


@router.get("/commute")
async def get_commute(user_id: UserId, ctx: Ctx) -> dict[str, Any]:
    """The commute route with roadside PM2.5 at today's departure times (morning and evening),
    and what each way of travelling would mean per hour on that route."""
    return await commute_service.commute_view(ctx, user_id)


@router.post("/visits", status_code=status.HTTP_202_ACCEPTED)
async def post_visits(body: VisitsIn, user_id: UserId, ctx: Ctx) -> dict[str, int]:
    """Geofence visits from the phone (home / office / away). Only enter and exit times are
    sent, never a GPS trail."""
    n = await profile_service.add_visits(
        ctx, user_id, [VisitRow(v.place, v.start, v.end, v.activity) for v in body.visits]
    )
    return {"accepted": n}


@router.post("/devices", status_code=status.HTTP_204_NO_CONTENT)
async def post_device(body: DeviceIn, user_id: UserId, ctx: Ctx) -> None:
    await profile_service.register_device(ctx, user_id, body.fcm_token, body.platform)


@router.delete("/devices/{fcm_token}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_device(
    fcm_token: Annotated[str, Path(max_length=4096)], user_id: UserId, ctx: Ctx
) -> None:
    await profile_service.remove_device(ctx, user_id, fcm_token)


@router.delete("", status_code=status.HTTP_204_NO_CONTENT)
async def delete_me(user_id: UserId, ctx: Ctx) -> None:
    """Delete the account and everything stored about it. Cannot be undone."""
    await profile_service.delete_account(ctx, user_id)


@router.get("/footprint")
async def get_footprint(user_id: UserId, ctx: Ctx) -> dict[str, Any]:
    """Estimated CO2 of the commute, every way of making it, and the best realistic swap
    (e.g. two days a week by metro). Climate, not the PM2.5 behind Lung Load. Ranges, with
    the published sources the factors come from."""
    return await footprint_service.footprint(ctx, user_id)
