"""Integration tests: real Postgres + PostGIS and Valkey (`make up`), fake external APIs.

A fresh `lung_test` database is created and migrated once per run; tables are emptied
between tests. Valkey uses database 15, flushed per test. The queue is an in-memory fake,
except in test_queue.py which talks to ElasticMQ.
"""

import asyncio
import os
from collections.abc import AsyncIterator, Iterator
from datetime import UTC, date, datetime, time, timedelta
from typing import Any
from uuid import UUID

import asyncpg
import httpx
import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import text

from lung.domain.air import HourlyAir
from lung.domain.geo import LatLon, cell_id
from lung.infra.cache import Cache
from lung.infra.db import Database
from lung.integrations.geocoder import GeoPlace
from lung.integrations.google_auth import GoogleIdentity, InvalidGoogleTokenError
from lung.integrations.open_meteo import PlaceForecast
from lung.integrations.openrouteservice import Route, RouteOption, RouteSample
from lung.repositories import places as places_repo
from lung.repositories import profiles as profiles_repo
from lung.repositories import schedules as schedules_repo
from lung.repositories import users as users_repo
from lung.repositories.places import PlaceRow, SourceRow
from lung.repositories.profiles import ProfileRow
from lung.repositories.schedules import ScheduleRow
from lung.services import route_service
from lung.services.context import AppContext
from lung.services.notifier import Push
from lung.settings import Settings

pytestmark = pytest.mark.integration

ADMIN_DSN = os.environ.get("TEST_ADMIN_DSN", "postgresql://lung:lung@localhost:55432/lung")
TEST_DB = "lung_test"
TEST_URL = f"postgresql+asyncpg://lung:lung@localhost:55432/{TEST_DB}"
VALKEY_TEST_URL = "redis://localhost:6379/15"
API_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(__file__)))

NOW = datetime(2026, 10, 4, 6, 0, tzinfo=UTC)  # 11:30 in Delhi
HOME = LatLon(28.6139, 77.2090)
OFFICE = LatLon(28.5355, 77.3910)


async def _recreate_db() -> None:
    conn = await asyncpg.connect(ADMIN_DSN)
    try:
        await conn.execute(
            "SELECT pg_terminate_backend(pid) FROM pg_stat_activity WHERE datname = $1", TEST_DB
        )
        await conn.execute(f'DROP DATABASE IF EXISTS "{TEST_DB}"')
        await conn.execute(f'CREATE DATABASE "{TEST_DB}"')
    finally:
        await conn.close()


async def _partitions_around_test_clock() -> None:
    """The migration makes air partitions from the real month on; the tests write around the
    fixed NOW, so make sure those months exist whatever the real date is."""
    conn = await asyncpg.connect(f"{ADMIN_DSN.rsplit('/', 1)[0]}/{TEST_DB}")
    try:
        first = date(NOW.year, NOW.month, 1)
        for k in range(-1, 3):
            y, m = divmod(first.month - 1 + k, 12)
            start = date(first.year + y, m + 1, 1)
            y2, m2 = divmod(start.month, 12)
            end = date(start.year + y2, m2 + 1, 1)
            await conn.execute(
                f"CREATE TABLE IF NOT EXISTS air_readings_{start:%Y_%m} PARTITION OF air_readings "
                f"FOR VALUES FROM ('{start}T00:00:00+00') TO ('{end}T00:00:00+00')"
            )
    finally:
        await conn.close()


@pytest.fixture(scope="session", autouse=True)
def migrated_db() -> Iterator[None]:
    asyncio.run(_recreate_db())
    os.environ["DATABASE_URL"] = TEST_URL
    from lung.settings import get_settings

    get_settings.cache_clear()
    cfg = Config(os.path.join(API_ROOT, "alembic.ini"))
    cfg.set_main_option("script_location", os.path.join(API_ROOT, "migrations"))
    command.upgrade(cfg, "head")
    asyncio.run(_partitions_around_test_clock())
    yield


# ---------------------------------------------------------------- fakes


class FakeQueue:
    def __init__(self) -> None:
        self.sent: list[tuple[str, dict[str, Any], int]] = []

    async def send(self, url: str, body: dict[str, Any], delay_s: int = 0) -> None:
        self.sent.append((url, dict(body), delay_s))

    async def send_many(self, url: str, bodies: list[dict[str, Any]]) -> None:
        for b in bodies:
            self.sent.append((url, dict(b), 0))

    async def ping(self, url: str) -> bool:
        return True

    def of_type(self, kind: str) -> list[dict[str, Any]]:
        return [b for _, b, _ in self.sent if b.get("type") == kind]

    async def close(self) -> None:
        pass


class FakeAir:
    """Same PM2.5 everywhere: 100 at night, 200 during 08-10 and 17-19 UTC+5:30 rush."""

    def __init__(self) -> None:
        self.calls: list[tuple[float, float]] = []

    async def hourly(self, lat: float, lon: float) -> list[HourlyAir]:
        self.calls.append((lat, lon))
        start = NOW.replace(hour=0) - timedelta(days=1)
        out = []
        for i in range(24 * 4):
            h = start + timedelta(hours=i)
            local_hour = (h + timedelta(hours=5, minutes=30)).hour
            pm = 200.0 if local_hour in (8, 9, 17, 18) else 100.0
            out.append(HourlyAir(h, pm, pm * 1.6, 2.0, 300.0))
        return out

    async def current_many(self, points: list[tuple[float, float]]) -> list[float | None]:
        # Cleaner the further north: lets tests tell points apart. None = no data (ocean).
        self.calls.extend(points)
        return [None if lat < -60 else round(150 - lat, 1) for lat, _ in points]

    async def place_forecast(self, lat: float, lon: float, days: int) -> PlaceForecast:
        self.calls.append((lat, lon))
        start = NOW.replace(hour=0) - timedelta(days=1)
        hours = []
        for i in range(24 * (days + 1)):
            h = start + timedelta(hours=i)
            local_hour = (h + timedelta(hours=5, minutes=30)).hour
            pm = 40.0 if 13 <= local_hour <= 15 else 90.0
            hours.append((h, pm, pm * 1.5))
        return PlaceForecast(lat, lon, 19800, hours)


class FakeGeocoder:
    def __init__(self) -> None:
        self.calls: list[str] = []
        self.nominatim_down = False

    async def nominatim_search(
        self, q: str, near: tuple[float, float] | None, limit: int
    ) -> list[GeoPlace]:
        self.calls.append(f"nominatim:{q}")
        if self.nominatim_down:
            raise RuntimeError("nominatim is down")
        return [GeoPlace(q.title(), "Ghaziabad, Uttar Pradesh", 28.61, 77.43)]

    async def nominatim_reverse(self, lat: float, lon: float) -> GeoPlace | None:
        self.calls.append("nominatim:reverse")
        return GeoPlace("Jail Road", "New Delhi, Delhi", lat, lon)

    async def photon_search(
        self, q: str, near: tuple[float, float] | None, limit: int
    ) -> list[GeoPlace]:
        self.calls.append(f"photon:{q}")
        return [GeoPlace(q.title(), "from Photon", 28.6, 77.4)]


class FakeRoutes:
    async def directions(
        self,
        start: LatLon,
        end: LatLon,
        profile: str,
        alternatives: int,
        every_km: float,
        max_points: int,
    ) -> list[RouteOption]:
        mid = LatLon((start.lat + end.lat) / 2, (start.lon + end.lon) / 2)
        north = LatLon(mid.lat + 0.3, mid.lon)  # a detour through cleaner air (further north)
        speed = {"driving-car": 30, "cycling-regular": 14, "foot-walking": 5}[profile]

        def option(points: list[LatLon], km: float, road: str) -> RouteOption:
            return RouteOption(
                line=points,
                samples=[RouteSample(p, road) for p in points],
                distance_km=km,
                duration_min=km / speed * 60,
            )

        out = [option([start, mid, end], 20.0, "trunk")]
        if profile == "driving-car" and alternatives > 1:
            out.append(option([start, north, end], 26.0, "secondary"))
        return out

    async def route(
        self, home: LatLon, office: LatLon, mode: str, every_km: float, max_points: int
    ) -> Route:
        mid = LatLon((home.lat + office.lat) / 2, (home.lon + office.lon) / 2)
        return Route(
            [
                RouteSample(home, "residential"),
                RouteSample(mid, "trunk"),
                RouteSample(office, "secondary"),
            ],
            distance_km=21.0,
        )


class SpyNotifier:
    def __init__(self) -> None:
        self.sent: list[tuple[list[str], Push]] = []

    async def send(self, tokens: list[str], push: Push) -> list[str]:
        self.sent.append((tokens, push))
        return [t for t in tokens if t.startswith("dead")]


class FakeMailer:
    def __init__(self) -> None:
        self.sent: list[tuple[str, str, str]] = []

    async def send(self, to: str, subject: str, body: str) -> None:
        self.sent.append((to, subject, body))

    def last_code(self, to: str) -> str:
        import re

        body = next(b for t, _, b in reversed(self.sent) if t == to)
        m = re.search(r"\b(\d{6})\b", body)
        assert m, body
        return m.group(1)


class FakeGoogle:
    """Accepts tokens of the form 'google:<sub>:<email>[:unverified]'."""

    async def verify(self, id_token: str) -> GoogleIdentity:
        parts = id_token.split(":")
        if parts[0] != "google" or len(parts) < 3:
            raise InvalidGoogleTokenError("bad token")
        return GoogleIdentity(parts[1], parts[2], email_verified=parts[-1] != "unverified")


# ---------------------------------------------------------------- fixtures


@pytest.fixture
def settings() -> Settings:
    return Settings(
        database_url=TEST_URL,
        valkey_url=VALKEY_TEST_URL,
        sqs_ingest_url="ingest",
        warm_areas=False,  # tests that want them switch them on
        sqs_user_url="user",
        uncertainty_runs=40,
    )


@pytest.fixture
async def client(ctx: AppContext) -> AsyncIterator[httpx.AsyncClient]:
    from lung.main import create_app

    transport = httpx.ASGITransport(app=create_app(ctx))
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as c:
        yield c


@pytest.fixture
async def ctx(settings: Settings) -> AsyncIterator[AppContext]:
    db = Database(settings)
    async with db.session() as s:
        tables = "users, air_readings, fire_events"  # users cascades to every user-owned table
        await s.execute(text(f"TRUNCATE {tables} CASCADE"))
    cache = Cache(settings.valkey_url)
    await cache._client.flushdb()
    context = AppContext(
        settings=settings,
        db=db,
        cache=cache,
        queue=FakeQueue(),  # type: ignore[arg-type]
        air=FakeAir(),
        routes=None,
        notifier=SpyNotifier(),
        mailer=FakeMailer(),
        google=FakeGoogle(),
        clock=lambda: NOW,
        geocoder=FakeGeocoder(),
    )
    yield context
    await cache.close()
    await db.close()


async def make_user(
    ctx: AppContext,
    *,
    office_days: tuple[int, ...] = (1, 2, 3, 4, 5, 6, 7),
    cooking: bool = False,
    route: bool = True,
) -> UUID:
    res = ctx.settings.cell_resolution_deg
    sources = (SourceRow("cooking_lpg", time(19, 30), 45),) if cooking else ()
    async with ctx.db.session() as s:
        uid = await users_repo.create(s)
        await profiles_repo.upsert(
            s,
            ProfileRow(
                uid, age=34, sex="man", sensitive=False, weight_kg=None, timezone="Asia/Kolkata"
            ),
        )
        await places_repo.upsert(
            s,
            uid,
            PlaceRow(
                "home",
                "Home",
                HOME.lat,
                HOME.lon,
                cell_id(HOME.lat, HOME.lon, res),
                size="2bhk",
                sources=sources,
            ),
        )
        await places_repo.upsert(
            s,
            uid,
            PlaceRow(
                "office", "Office", OFFICE.lat, OFFICE.lon, cell_id(OFFICE.lat, OFFICE.lon, res)
            ),
        )
        await schedules_repo.upsert(
            s,
            uid,
            ScheduleRow(
                time(7),
                time(8, 30),
                time(9),
                time(17, 30),
                time(18),
                time(23),
                "metro",
                office_days=office_days,
            ),
        )
    if route:  # as the profile save does: a straight line straight away
        await route_service.compute_route(ctx, uid)
        ctx.queue.sent.clear()  # type: ignore[attr-defined]
        await ctx.cache.delete(f"recompute-queued:{uid}")
    return uid


def local_today() -> date:
    return (NOW + timedelta(hours=5, minutes=30)).date()
