from datetime import UTC, datetime, time, timedelta

import pytest
from sqlalchemy import text

from lung.domain.air import HourlyAir
from lung.repositories import air_readings as air_repo
from lung.repositories import alerts as alerts_repo
from lung.repositories import places as places_repo
from lung.repositories import routes as routes_repo
from lung.repositories import schedules as schedules_repo
from lung.repositories import users as users_repo
from lung.repositories.routes import RoutePointRow
from lung.services.context import AppContext

from .conftest import HOME, local_today, make_user

pytestmark = pytest.mark.integration


async def test_places_round_trip_with_sources(ctx: AppContext) -> None:
    uid = await make_user(ctx, cooking=True)
    async with ctx.db.session() as s:
        places = await places_repo.for_user(s, uid)
    home = places["home"]
    assert home.lat == pytest.approx(HOME.lat)
    assert home.cell_id == "28.6_77.2"
    assert home.size == "2bhk"
    assert [(x.kind, x.start_time, x.minutes) for x in home.sources] == [
        ("cooking_lpg", time(19, 30), 45)
    ]
    assert places["office"].sources == ()


async def test_schedule_check_constraint_rejects_out_of_order(ctx: AppContext) -> None:
    uid = await make_user(ctx)
    async with ctx.db.session() as s:
        sched = await schedules_repo.get(s, uid)
    assert sched is not None
    bad = sched.__class__(**{**sched.__dict__, "arrive_office": time(8, 0)})
    with pytest.raises(Exception, match="check constraint"):
        async with ctx.db.session() as s:
            await schedules_repo.upsert(s, uid, bad)


async def test_air_upsert_is_idempotent_and_partitioned(ctx: AppContext) -> None:
    hour = datetime(2026, 10, 4, 3, tzinfo=UTC)
    rows = [HourlyAir(hour, 150.0, 250.0, 1.5, 270.0)]
    async with ctx.db.session() as s:
        await air_repo.upsert_many(s, "28.6_77.2", "open_meteo", rows)
        await air_repo.upsert_many(
            s, "28.6_77.2", "open_meteo", [HourlyAir(hour, 160.0, 250.0, 1.5, 270.0)]
        )
        got = await air_repo.pm25_for(s, ["28.6_77.2"], hour, hour + timedelta(hours=1))
        part = (
            await s.execute(
                text(
                    "SELECT tableoid::regclass::text FROM air_readings WHERE cell_id = '28.6_77.2'"
                )
            )
        ).scalar_one()
    assert got == {"28.6_77.2": {hour: 160.0}}
    assert part == "air_readings_2026_10"


async def test_cells_and_users_include_route_points(ctx: AppContext) -> None:
    uid = await make_user(ctx, route=False)
    async with ctx.db.session() as s:
        await routes_repo.replace(
            s, uid, "straight_line", 20.0, [RoutePointRow(28.58, 77.30, "28.6_77.3", "unknown")]
        )
        cells = await places_repo.cells_in_use(s)
        users = await places_repo.users_in_cell(s, "28.6_77.3")
    assert cells == ["28.5_77.4", "28.6_77.2", "28.6_77.3"]
    assert users == [uid]


async def test_alert_claim_only_once(ctx: AppContext) -> None:
    uid = await make_user(ctx)
    async with ctx.db.session() as s:
        first = await alerts_repo.claim(s, uid, "red_tomorrow", local_today())
        again = await alerts_repo.claim(s, uid, "red_tomorrow", local_today())
    assert (first, again) == (True, False)


async def test_deleting_user_removes_everything(ctx: AppContext) -> None:
    uid = await make_user(ctx, cooking=True)
    async with ctx.db.session() as s:
        await users_repo.delete(s, uid)
        left = (
            await s.execute(
                text(
                    "SELECT (SELECT count(*) FROM profiles) + (SELECT count(*) FROM places) "
                    "+ (SELECT count(*) FROM indoor_sources) + (SELECT count(*) FROM schedules)"
                )
            )
        ).scalar_one()
    assert left == 0
