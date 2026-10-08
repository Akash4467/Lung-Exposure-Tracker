"""One small handler per message type. Every handler is safe to run twice."""

from collections.abc import Awaitable, Callable
from datetime import date, datetime
from typing import Any
from uuid import UUID

import structlog

from lung.domain.errors import Retryable
from lung.services import alert_service, fire_service, ingest_service, route_service, score_service
from lung.services.context import AppContext
from lung.services.plan import ProfileIncompleteError

log = structlog.get_logger()

Handler = Callable[[AppContext, dict[str, Any]], Awaitable[None]]


async def handle_tick(ctx: AppContext, body: dict[str, Any]) -> None:
    at = datetime.fromisoformat(body["at"]) if "at" in body else ctx.clock()
    await ingest_service.tick(ctx, at)


async def handle_fetch(ctx: AppContext, body: dict[str, Any]) -> None:
    await ingest_service.fetch(ctx, body["cell_id"], force=bool(body.get("force")))


async def handle_route(ctx: AppContext, body: dict[str, Any]) -> None:
    await route_service.compute_route(ctx, UUID(body["user_id"]))


async def handle_recompute(ctx: AppContext, body: dict[str, Any]) -> None:
    user_id = UUID(body["user_id"])
    try:
        out = await score_service.recompute(ctx, user_id)
    except ProfileIncompleteError:
        log.info("recompute_skipped", user_id=str(user_id), reason="profile incomplete")
        return
    except score_service.NoAirDataError as e:
        # Ask for the missing cells now and try again after the visibility timeout.
        await ctx.queue.send_many(
            ctx.settings.sqs_ingest_url,
            [ingest_service.fetch_msg(c) | {"force": True} for c in e.cells],
        )
        raise Retryable(str(e)) from e

    alerts = []
    if out.tomorrow_band == "red":
        alerts.append("red_tomorrow")
    if out.fire_risk == "high":
        alerts.append("smoke_tomorrow")
    for a in alerts:
        await ctx.queue.send(
            ctx.settings.sqs_user_url, alert_service.alert_msg(str(user_id), a, out.tomorrow)
        )


async def handle_alert(ctx: AppContext, body: dict[str, Any]) -> None:
    await alert_service.send(
        ctx, UUID(body["user_id"]), body["alert"], date.fromisoformat(body["date"])
    )


async def handle_fires(ctx: AppContext, body: dict[str, Any]) -> None:
    await fire_service.refresh(ctx, force=bool(body.get("force")))


HANDLERS: dict[str, Handler] = {
    "tick": handle_tick,
    "fetch": handle_fetch,
    "route": handle_route,
    "recompute": handle_recompute,
    "alert": handle_alert,
    "fires": handle_fires,
}
