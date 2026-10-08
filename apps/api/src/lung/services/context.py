"""Everything a service needs, built once per process (API or worker) and passed in."""

from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from typing import Protocol

import httpx

from lung.domain.geo import LatLon
from lung.engine.config import EngineConfig
from lung.infra.cache import Cache
from lung.infra.db import Database
from lung.infra.engine_config import load_config
from lung.infra.queue import Queue
from lung.integrations.brevo import BrevoMailer
from lung.integrations.fcm import FcmNotifier
from lung.integrations.firms import FireDetection, FirmsClient
from lung.integrations.geocoder import Geocoder, GeoPlace
from lung.integrations.google_auth import GoogleIdentity, GoogleVerifier
from lung.integrations.open_meteo import OpenMeteoClient, PlaceForecast
from lung.integrations.openrouteservice import OpenRouteServiceClient, Route, RouteOption
from lung.integrations.stations import CpcbClient, OpenAQClient, StationReading
from lung.services.mailer import LogMailer, Mailer
from lung.services.notifier import LogNotifier, Notifier
from lung.settings import Settings


class AirSource(Protocol):
    async def hourly(self, lat: float, lon: float) -> list: ...  # type: ignore[type-arg]

    async def current_many(self, points: list[tuple[float, float]]) -> list[float | None]: ...

    async def place_forecast(self, lat: float, lon: float, days: int) -> PlaceForecast: ...


class RouteSource(Protocol):
    async def route(
        self, home: LatLon, office: LatLon, mode: str, every_km: float, max_points: int
    ) -> Route: ...

    async def directions(
        self,
        start: LatLon,
        end: LatLon,
        profile: str,
        alternatives: int,
        every_km: float,
        max_points: int,
    ) -> list[RouteOption]: ...


class FireSource(Protocol):
    async def fires(
        self, west: float, south: float, east: float, north: float, days: int
    ) -> list[FireDetection]: ...


class StationSource(Protocol):
    async def near(
        self, lat: float, lon: float, radius_km: float, max_age: timedelta, now: datetime
    ) -> list[StationReading]: ...


class StationListSource(Protocol):
    async def all_pm25(self) -> list[StationReading]: ...


class GeoSource(Protocol):
    async def nominatim_search(
        self, q: str, near: tuple[float, float] | None, limit: int
    ) -> list[GeoPlace]: ...

    async def nominatim_reverse(self, lat: float, lon: float) -> GeoPlace | None: ...

    async def photon_search(
        self, q: str, near: tuple[float, float] | None, limit: int
    ) -> list[GeoPlace]: ...


class IdentityVerifier(Protocol):
    async def verify(self, id_token: str) -> GoogleIdentity: ...


def utc_now() -> datetime:
    return datetime.now(UTC)


@dataclass
class AppContext:
    settings: Settings
    db: Database
    cache: Cache
    queue: Queue
    air: AirSource
    routes: RouteSource | None  # None when ORS_API_KEY is not set
    notifier: Notifier
    mailer: Mailer
    google: IdentityVerifier
    cfg: EngineConfig = field(default_factory=load_config)
    clock: Callable[[], datetime] = utc_now
    geocoder: GeoSource | None = None
    fires: FireSource | None = None  # None when FIRMS_MAP_KEY is not set
    openaq: StationSource | None = None  # None when OPENAQ_API_KEY is not set
    cpcb: StationListSource | None = None  # None when CPCB_API_KEY is not set


async def build_context(settings: Settings, http: httpx.AsyncClient) -> AppContext:
    queue = Queue(settings)
    await queue.start()
    key = settings.ors_api_key.get_secret_value() if settings.ors_api_key else None
    return AppContext(
        settings=settings,
        db=Database(settings),
        cache=Cache(settings.valkey_url),
        queue=queue,
        air=OpenMeteoClient(
            http,
            settings.open_meteo_air_base,
            settings.open_meteo_weather_base,
            settings.air_past_days,
            settings.air_forecast_days,
        ),
        routes=OpenRouteServiceClient(http, settings.ors_base, key) if key else None,
        notifier=_notifier(settings, http),
        mailer=_mailer(settings, http),
        google=GoogleVerifier(settings.google_client_ids),
        geocoder=Geocoder(http, settings.nominatim_base, settings.photon_base),
        fires=(
            FirmsClient(
                http,
                settings.firms_base,
                settings.firms_map_key.get_secret_value(),
                settings.firms_source,
            )
            if settings.firms_map_key
            else None
        ),
        openaq=(
            OpenAQClient(http, settings.openaq_base, settings.openaq_api_key.get_secret_value())
            if settings.openaq_api_key
            else None
        ),
        cpcb=(
            CpcbClient(http, settings.cpcb_base, settings.cpcb_api_key.get_secret_value())
            if settings.cpcb_api_key
            else None
        ),
    )


def _notifier(settings: Settings, http: httpx.AsyncClient) -> Notifier:
    if settings.fcm_project_id and settings.fcm_service_account_json:
        return FcmNotifier(
            http, settings.fcm_project_id, settings.fcm_service_account_json.get_secret_value()
        )
    return LogNotifier()


def _mailer(settings: Settings, http: httpx.AsyncClient) -> Mailer:
    if settings.brevo_api_key:
        return BrevoMailer(
            http,
            settings.brevo_base,
            settings.brevo_api_key.get_secret_value(),
            settings.mail_from,
            settings.mail_from_name,
        )
    if settings.is_production:
        raise RuntimeError("BREVO_API_KEY is required in production")
    return LogMailer()


async def close_context(ctx: AppContext) -> None:
    await ctx.queue.close()
    await ctx.cache.close()
    await ctx.db.close()
