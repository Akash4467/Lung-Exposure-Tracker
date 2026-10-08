"""Local only: create a demo user (Delhi home, Noida office) and queue the first jobs.

uv run python -m lung.devtools.seed
"""

import asyncio
from datetime import time
from uuid import UUID

import httpx

from lung.domain.geo import cell_id
from lung.repositories import places as places_repo
from lung.repositories import profiles as profiles_repo
from lung.repositories import schedules as schedules_repo
from lung.repositories import users as users_repo
from lung.repositories.places import PlaceRow, SourceRow
from lung.repositories.profiles import ProfileRow
from lung.repositories.schedules import ScheduleRow
from lung.services import route_service
from lung.services.context import build_context, close_context
from lung.settings import get_settings

DEMO_USER = UUID("00000000-0000-4000-8000-00000000d3e0")


async def main() -> None:
    settings = get_settings()
    if settings.is_production:
        raise SystemExit("refusing to seed a production database")
    res = settings.cell_resolution_deg
    async with httpx.AsyncClient(timeout=settings.http_timeout_s) as http:
        ctx = await build_context(settings, http)
        try:
            async with ctx.db.session() as s:
                await users_repo.create(s, DEMO_USER)
                await profiles_repo.upsert(
                    s, ProfileRow(DEMO_USER, 34, "man", False, 72.0, "Asia/Kolkata")
                )
                await places_repo.upsert(
                    s,
                    DEMO_USER,
                    PlaceRow(
                        "home",
                        "Home (Connaught Place)",
                        28.6315,
                        77.2167,
                        cell_id(28.6315, 77.2167, res),
                        size="2bhk",
                        sources=(
                            SourceRow("cooking_lpg", time(19, 30), 45),
                            SourceRow("mosquito_coil", time(22, 0), 480),
                        ),
                    ),
                )
                await places_repo.upsert(
                    s,
                    DEMO_USER,
                    PlaceRow(
                        "office",
                        "Office (Noida Sec 62)",
                        28.6270,
                        77.3727,
                        cell_id(28.6270, 77.3727, res),
                    ),
                )
                await schedules_repo.upsert(
                    s,
                    DEMO_USER,
                    ScheduleRow(
                        time(7), time(8, 30), time(9, 30), time(18), time(19), time(23), "metro"
                    ),
                )
            source = await route_service.compute_route(ctx, DEMO_USER)
            await ctx.queue.send(settings.sqs_ingest_url, {"type": "tick"})
            print(f"demo user {DEMO_USER} ready; route: {source}; tick queued")
        finally:
            await close_context(ctx)


if __name__ == "__main__":
    asyncio.run(main())
