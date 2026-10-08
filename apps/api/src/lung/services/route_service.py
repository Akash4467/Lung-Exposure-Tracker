"""Work out and store the commute route once, when home, office or commute mode changes.

Every user always has a stored route: saving a profile stores a straight line at once (no
API call), and OpenRouteService replaces it when a key is configured. So the hourly tick
always knows every cell a user needs.
"""

from uuid import UUID

import httpx
import structlog

from lung.domain.errors import Retryable
from lung.domain.geo import LatLon, cell_id, haversine_km, sample_line
from lung.integrations.openrouteservice import SOURCE as ORS
from lung.repositories import places as places_repo
from lung.repositories import routes as routes_repo
from lung.repositories import schedules as schedules_repo
from lung.repositories.routes import RoutePointRow
from lung.services.context import AppContext
from lung.services.ingest_service import fetch_msg, queue_recompute

log = structlog.get_logger()

STRAIGHT_LINE = "straight_line"


async def compute_route(ctx: AppContext, user_id: UUID, use_provider: bool = True) -> str:
    """Returns the source used: "openrouteservice" or "straight_line".

    `use_provider=False` stores a straight line without calling ORS (used inline when a
    profile is saved, so the request stays fast; the route job then upgrades it)."""
    async with ctx.db.session() as s:
        places = await places_repo.for_user(s, user_id)
        sched = await schedules_repo.get(s, user_id)
    if "home" not in places or "office" not in places or sched is None:
        return "skipped"
    home = LatLon(places["home"].lat, places["home"].lon)
    office = LatLon(places["office"].lat, places["office"].lon)
    st = ctx.settings
    res = st.cell_resolution_deg

    source, distance, points = STRAIGHT_LINE, haversine_km(home, office), []
    if use_provider and ctx.routes is not None:
        try:
            route = await ctx.routes.route(
                home, office, sched.commute_mode, st.route_sample_km, st.route_max_points
            )
            source, distance = ORS, route.distance_km
            points = [
                RoutePointRow(
                    p.point.lat, p.point.lon, cell_id(p.point.lat, p.point.lon, res), p.road_class
                )
                for p in route.samples
            ]
        except Retryable:
            raise
        except (httpx.HTTPStatusError, KeyError, IndexError) as e:
            # No route found, bad key, odd response: a straight line is still useful.
            log.warning("route_fallback", user_id=str(user_id), error=type(e).__name__)
    if not points:
        points = [
            RoutePointRow(p.lat, p.lon, cell_id(p.lat, p.lon, res), "unknown")
            for p, _ in sample_line([home, office], st.route_sample_km, st.route_max_points)
        ]

    async with ctx.db.session() as s:
        await routes_repo.replace(s, user_id, source, distance, points)
    cells = sorted({p.cell_id for p in points})
    await ctx.queue.send_many(st.sqs_ingest_url, [fetch_msg(c) for c in cells])
    await queue_recompute(ctx, user_id)
    log.info("route_stored", user_id=str(user_id), source=source, points=len(points))
    return source
