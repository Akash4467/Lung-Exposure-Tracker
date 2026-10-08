"""Lung Load: what the person was actually doing (a manual log, the phone's activity
recognition, or Health Connect heart rate and steps). Heart rate or steps per minute become a
measured exertion (MET) here, so the engine only ever sees a kind and a MET.
"""

from dataclasses import dataclass
from datetime import date, datetime, timedelta
from uuid import UUID
from zoneinfo import ZoneInfo

from lung.domain.errors import InvalidInput, NotFound
from lung.engine.activity import kind_from_met, met_from_cadence, met_from_heart_rate
from lung.engine.models import Activity
from lung.repositories import activity as activity_repo
from lung.repositories import profiles as profiles_repo
from lung.repositories.activity import ActivityRow
from lung.services import ingest_service, score_service
from lung.services.context import AppContext
from lung.services.plan import ProfileIncompleteError

MAX_PER_CALL = 500
MAX_AGE = timedelta(hours=48)
MAX_LENGTH = timedelta(hours=12)
CLOCK_SKEW = timedelta(minutes=5)


@dataclass(frozen=True)
class ActivityLog:
    start: datetime
    end: datetime
    kind: Activity | None = None  # None: worked out from the measured exertion
    met: float | None = None
    outdoors: bool | None = None
    source: str = "manual"
    heart_rate: float | None = None  # average bpm over the interval
    resting_hr: float | None = None  # the person's resting heart rate, if the watch knows it
    steps_per_min: float | None = None


def to_row(log: ActivityLog, age: int, ctx: AppContext) -> ActivityRow:
    cfg = ctx.cfg
    met = log.met
    if met is None and log.heart_rate is not None:
        met = met_from_heart_rate(log.heart_rate, age, cfg, log.resting_hr)
    elif met is None and log.steps_per_min is not None:
        met = met_from_cadence(log.steps_per_min, cfg)
    kind = log.kind
    if kind is None:
        if met is None:
            raise InvalidInput(
                "say what you were doing, or send heart rate or steps", "bad_activity"
            )
        # Heart rate alone can't tell walking from, say, a gym bike: only steps mean moving.
        kind = kind_from_met(met, cfg, moving=log.steps_per_min is not None)
    return ActivityRow(
        start_at=log.start,
        end_at=log.end,
        kind=kind,
        met=round(met, 2) if met is not None else None,
        outdoors=log.outdoors,
        source=log.source,
        heart_rate=log.heart_rate,
        steps_per_min=log.steps_per_min,
    )


async def add(ctx: AppContext, user_id: UUID, logs: list[ActivityLog]) -> list[int]:
    if len(logs) > MAX_PER_CALL:
        raise InvalidInput(f"at most {MAX_PER_CALL} activities per call", "too_many_activities")
    now = ctx.clock()
    for a in logs:
        if a.end <= a.start:
            raise InvalidInput("an activity must end after it starts", "bad_activity")
        if a.end - a.start > MAX_LENGTH:
            raise InvalidInput("an activity can be at most 12 hours long", "bad_activity")
        if a.start < now - MAX_AGE or a.end > now + CLOCK_SKEW:
            raise InvalidInput("activities must be within the last 48 hours", "bad_activity")
    async with ctx.db.session() as s:
        profile = await profiles_repo.get(s, user_id)
        if profile is None:
            raise NotFound("finish onboarding first", "profile_incomplete")
        rows = [to_row(a, profile.age, ctx) for a in logs]
        synced = [r for r in rows if r.source == "health_connect"]
        if synced:
            # A re-sync of the same hours replaces what Health Connect sent before.
            await activity_repo.delete_source_between(
                s,
                user_id,
                "health_connect",
                min(r.start_at for r in synced),
                max(r.end_at for r in synced),
            )
        ids = await activity_repo.add_many(s, user_id, rows)
    if any(a.source == "manual" for a in logs):
        await _recompute_now(ctx, user_id)  # the person is looking at the screen
    elif logs:
        await ingest_service.queue_recompute(ctx, user_id)
    return ids


async def for_day(
    ctx: AppContext, user_id: UUID, day: date | None = None
) -> tuple[date, list[ActivityRow]]:
    """The activities that overlap a local day (today by default)."""
    async with ctx.db.session() as s:
        profile = await profiles_repo.get(s, user_id)
        if profile is None:
            raise NotFound("finish onboarding first", "profile_incomplete")
        tz = ZoneInfo(profile.timezone)
        day = day or ctx.clock().astimezone(tz).date()
        start = datetime.combine(day, datetime.min.time(), tzinfo=tz)
        rows = await activity_repo.between(s, user_id, start, start + timedelta(days=1))
    return day, rows


async def remove(ctx: AppContext, user_id: UUID, activity_id: int) -> None:
    async with ctx.db.session() as s:
        if not await activity_repo.delete(s, user_id, activity_id):
            raise NotFound("no such activity", "activity_not_found")
    await _recompute_now(ctx, user_id)


async def _recompute_now(ctx: AppContext, user_id: UUID) -> None:
    try:
        await score_service.recompute(ctx, user_id)
    except (score_service.NoAirDataError, ProfileIncompleteError):
        await ingest_service.queue_recompute(ctx, user_id)
