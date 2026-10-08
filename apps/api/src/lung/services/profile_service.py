"""The user's own data: profile, places, schedule, indoor details, visits, devices, account."""

from dataclasses import dataclass, replace
from datetime import timedelta
from uuid import UUID

import structlog

from lung.domain.errors import InvalidInput, NotFound
from lung.domain.geo import cell_id
from lung.engine.day import validate_schedule
from lung.engine.models import Schedule
from lung.repositories import accounts as accounts_repo
from lung.repositories import device_tokens as tokens_repo
from lung.repositories import places as places_repo
from lung.repositories import profiles as profiles_repo
from lung.repositories import schedules as schedules_repo
from lung.repositories import users as users_repo
from lung.repositories import visits as visits_repo
from lung.repositories.places import PlaceRow, SourceRow
from lung.repositories.profiles import ProfileRow
from lung.repositories.schedules import ScheduleRow
from lung.repositories.visits import VisitRow
from lung.services import ingest_service, route_service, score_service
from lung.services.context import AppContext
from lung.services.plan import ProfileIncompleteError

log = structlog.get_logger()

MAX_VISITS_PER_CALL = 200
VISIT_MAX_AGE = timedelta(hours=48)


@dataclass(frozen=True)
class FullProfile:
    profile: ProfileRow
    home: PlaceRow
    office: PlaceRow
    schedule: ScheduleRow


@dataclass(frozen=True)
class Me:
    user_id: UUID
    email: str | None
    email_verified: bool
    has_password: bool
    google_linked: bool
    onboarded: bool


@dataclass(frozen=True)
class IndoorUpdate:
    windows: str | None = None
    purifier: bool | None = None
    purifier_cadr_m3h: float | None = None
    clear_cadr: bool = False
    size: str | None = None
    sources: tuple[SourceRow, ...] | None = None  # None = leave as is; () = remove all


def _check_place(ctx: AppContext, p: PlaceRow) -> None:
    ind = ctx.cfg.indoor
    if p.size is not None and p.size not in ind.volume_m3:
        raise InvalidInput(f"unknown size {p.size!r}", "unknown_size")
    for src in p.sources:
        if src.kind not in ind.sources:
            raise InvalidInput(f"unknown indoor source {src.kind!r}", "unknown_source")


def _check_schedule(sc: ScheduleRow) -> None:
    try:
        validate_schedule(
            Schedule(
                sc.wake,
                sc.leave_home,
                sc.arrive_office,
                sc.leave_office,
                sc.arrive_home,
                sc.sleep,
                sc.commute_mode,  # type: ignore[arg-type]  # checked by the API schema
            )
        )
    except ValueError as e:
        raise InvalidInput(str(e), "bad_schedule") from e
    if any(d < 1 or d > 7 for d in sc.office_days):
        raise InvalidInput("office_days are ISO weekdays 1-7", "bad_schedule")


async def _recompute_now(ctx: AppContext, user_id: UUID) -> None:
    """Refresh scores right away so the app shows the change; fall back to the queue."""
    try:
        await score_service.recompute(ctx, user_id)
    except (score_service.NoAirDataError, ProfileIncompleteError):
        await ingest_service.queue_recompute(ctx, user_id)


async def me(ctx: AppContext, user_id: UUID) -> Me:
    async with ctx.db.session() as s:
        acct = await accounts_repo.by_id(s, user_id)
        if acct is None:
            raise NotFound("account not found")
        profile = await profiles_repo.get(s, user_id)
        places = await places_repo.for_user(s, user_id)
        sched = await schedules_repo.get(s, user_id)
    return Me(
        user_id=user_id,
        email=acct.email,
        email_verified=acct.email_verified,
        has_password=acct.password_hash is not None,
        google_linked=acct.google_sub is not None,
        onboarded=profile is not None and sched is not None and {"home", "office"} <= set(places),
    )


async def get_profile(ctx: AppContext, user_id: UUID) -> FullProfile:
    async with ctx.db.session() as s:
        profile = await profiles_repo.get(s, user_id)
        places = await places_repo.for_user(s, user_id)
        sched = await schedules_repo.get(s, user_id)
    if profile is None or sched is None or "home" not in places or "office" not in places:
        raise NotFound("finish onboarding first", "profile_incomplete")
    return FullProfile(profile, places["home"], places["office"], sched)


async def save_profile(
    ctx: AppContext,
    user_id: UUID,
    profile: ProfileRow,
    home: PlaceRow,
    office: PlaceRow,
    schedule: ScheduleRow,
) -> FullProfile:
    """Create or replace the whole onboarding profile in one go."""
    res = ctx.settings.cell_resolution_deg
    home = replace(home, type="home", cell_id=cell_id(home.lat, home.lon, res))
    office = replace(office, type="office", cell_id=cell_id(office.lat, office.lon, res))
    for p in (home, office):
        _check_place(ctx, p)
    _check_schedule(schedule)

    async with ctx.db.session() as s:
        before = await places_repo.for_user(s, user_id)
        old_sched = await schedules_repo.get(s, user_id)
        await profiles_repo.upsert(s, replace(profile, user_id=user_id))
        await places_repo.upsert(s, user_id, home)
        await places_repo.upsert(s, user_id, office)
        await schedules_repo.upsert(s, user_id, schedule)

    moved = (
        old_sched is None
        or old_sched.commute_mode != schedule.commute_mode
        or any(
            t not in before or (before[t].lat, before[t].lon) != (p.lat, p.lon)
            for t, p in (("home", home), ("office", office))
        )
    )
    if moved:
        # A straight line straight away, so every cell is known; the real route follows.
        await route_service.compute_route(ctx, user_id, use_provider=False)
        if ctx.routes is not None:
            await ctx.queue.send(
                ctx.settings.sqs_user_url, {"type": "route", "user_id": str(user_id)}
            )
    await _recompute_now(ctx, user_id)
    return await get_profile(ctx, user_id)


async def update_indoor(
    ctx: AppContext, user_id: UUID, place_type: str, upd: IndoorUpdate
) -> PlaceRow:
    async with ctx.db.session() as s:
        places = await places_repo.for_user(s, user_id)
        if place_type not in places:
            raise NotFound("finish onboarding first", "profile_incomplete")
        cur = places[place_type]
        new = replace(
            cur,
            windows=upd.windows or cur.windows,
            purifier=cur.purifier if upd.purifier is None else upd.purifier,
            purifier_cadr_m3h=None
            if upd.clear_cadr
            else (upd.purifier_cadr_m3h or cur.purifier_cadr_m3h),
            size=upd.size or cur.size,
            sources=cur.sources if upd.sources is None else upd.sources,
        )
        _check_place(ctx, new)
        await places_repo.upsert(s, user_id, new)
    await _recompute_now(ctx, user_id)
    return new


async def add_visits(ctx: AppContext, user_id: UUID, visits: list[VisitRow]) -> int:
    if len(visits) > MAX_VISITS_PER_CALL:
        raise InvalidInput(f"at most {MAX_VISITS_PER_CALL} visits per call", "too_many_visits")
    now = ctx.clock()
    for v in visits:
        if v.end_at <= v.start_at:
            raise InvalidInput("a visit must end after it starts", "bad_visit")
        if v.start_at < now - VISIT_MAX_AGE or v.end_at > now + timedelta(minutes=5):
            raise InvalidInput("visits must be within the last 48 hours", "bad_visit")
    async with ctx.db.session() as s:
        await visits_repo.add_many(s, user_id, visits)
    if visits:
        await ingest_service.queue_recompute(ctx, user_id)
    return len(visits)


async def register_device(ctx: AppContext, user_id: UUID, token: str, platform: str) -> None:
    async with ctx.db.session() as s:
        await tokens_repo.upsert(s, user_id, token, platform)


async def remove_device(ctx: AppContext, user_id: UUID, token: str) -> None:
    """Only the owner can unregister a token (e.g. on sign-out)."""
    async with ctx.db.session() as s:
        if await tokens_repo.owner(s, token) == user_id:
            await tokens_repo.delete(s, token)


async def delete_account(ctx: AppContext, user_id: UUID) -> None:
    """Every row the user owns goes (ON DELETE CASCADE), plus their cache entries."""
    async with ctx.db.session() as s:
        tz = p.timezone if (p := await profiles_repo.get(s, user_id)) else "Asia/Kolkata"
        await users_repo.delete(s, user_id)
    today = score_service.local_today(tz, ctx.clock())
    await ctx.cache.delete(
        score_service.score_cache_key(user_id, today, False),
        score_service.score_cache_key(user_id, today + timedelta(days=1), True),
        f"recompute-queued:{user_id}",
    )
    log.info("account_deleted", user_id=str(user_id))
