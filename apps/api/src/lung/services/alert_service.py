"""Calm, specific alerts, sent at most once per user, type and day."""

from datetime import date
from uuid import UUID

import structlog

from lung.repositories import alerts as alerts_repo
from lung.repositories import device_tokens as tokens_repo
from lung.services.context import AppContext
from lung.services.notifier import Push

log = structlog.get_logger()

MESSAGES = {
    "red_tomorrow": Push(
        title="Tomorrow's air looks poor",
        body="Your estimated exposure tomorrow is high. Open the app for the best times "
        "to be outside and simple ways to cut it.",
        data={"screen": "tomorrow"},
    ),
    "smoke_tomorrow": Push(
        title="Smoke risk tomorrow",
        body="Fires upwind may bring smoke tomorrow. Consider keeping windows closed and "
        "planning outdoor time for the cleaner hours.",
        data={"screen": "tomorrow"},
    ),
}


def alert_msg(user_id: str, alert: str, day: date) -> dict[str, str]:
    return {"type": "alert", "user_id": user_id, "alert": alert, "date": day.isoformat()}


async def send(ctx: AppContext, user_id: UUID, alert: str, day: date) -> bool:
    """True if a push went out. A repeat for the same user, type and day sends nothing."""
    push = MESSAGES[alert]
    async with ctx.db.session() as s:
        if not await alerts_repo.claim(s, user_id, alert, day):
            return False
        tokens = await tokens_repo.for_user(s, user_id)
    if not tokens:
        return False
    dead = await ctx.notifier.send(tokens, push)
    if dead:
        async with ctx.db.session() as s:
            for t in dead:
                await tokens_repo.delete(s, t)
    log.info("alert_sent", user_id=str(user_id), alert=alert, devices=len(tokens) - len(dead))
    return True
