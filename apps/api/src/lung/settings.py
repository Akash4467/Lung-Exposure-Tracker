"""Every setting comes from an environment variable, read once at startup."""

from functools import lru_cache
from typing import Annotated, Literal

from pydantic import Field, SecretStr, field_validator, model_validator
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict

DEV_JWT_SECRET = "dev-only-insecure-secret-change-me-0000"  # noqa: S105


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    env: Literal["local", "test", "demo", "scale"] = "local"
    log_level: str = "info"

    database_url: str = "postgresql+asyncpg://lung:lung@localhost:55432/lung"
    db_pool_size: int = 5
    valkey_url: str = "redis://localhost:6379/0"

    aws_region: str = "ap-south-1"
    # Set only locally, to point boto at ElasticMQ; empty in AWS.
    sqs_endpoint_url: str | None = None
    sqs_ingest_url: str = "http://localhost:9324/000000000000/ingest-jobs"
    sqs_user_url: str = "http://localhost:9324/000000000000/user-jobs"

    # Air data (Open-Meteo needs no key)
    open_meteo_air_base: str = "https://air-quality-api.open-meteo.com/v1"
    open_meteo_weather_base: str = "https://api.open-meteo.com/v1"
    air_past_days: int = 1
    # 3, not 2: Open-Meteo counts days in UTC, and for time zones ahead of UTC (India: +5:30)
    # "tomorrow" ends up to a day later than UTC tomorrow (e.g. 00:00-05:30 IST).
    air_forecast_days: int = 3
    cell_resolution_deg: float = 0.1
    # also fetch the popular areas in warm_areas.yaml every tick, before anyone lives there
    warm_areas: bool = True

    # Routes (optional key; without it routes fall back to a straight line)
    ors_api_key: SecretStr | None = None
    ors_base: str = "https://api.openrouteservice.org"
    nominatim_base: str = "https://nominatim.openstreetmap.org"
    firms_map_key: SecretStr | None = None  # free: firms.modaps.eosdis.nasa.gov/api/map_key
    firms_base: str = "https://firms.modaps.eosdis.nasa.gov"
    firms_source: str = "VIIRS_SNPP_NRT"
    openaq_api_key: SecretStr | None = None  # free: explore.openaq.org → account → API key
    openaq_base: str = "https://api.openaq.org"
    cpcb_api_key: SecretStr | None = None  # free: data.gov.in → sign up → API key
    cpcb_base: str = "https://api.data.gov.in"
    photon_base: str = "https://photon.komoot.io"
    route_sample_km: float = 1.0
    route_max_points: int = 20

    http_timeout_s: float = 15.0
    worker_concurrency: int = 4
    score_cache_ttl_s: int = 900
    uncertainty_runs: int = 200
    # Local only: the worker queues a tick itself every N minutes (EventBridge does it in AWS).
    local_tick_minutes: int | None = None

    cors_origins: Annotated[list[str], NoDecode] = Field(default_factory=list)

    # ---- auth
    jwt_secret: SecretStr = SecretStr(DEV_JWT_SECRET)
    jwt_issuer: str = "lung-api"
    jwt_audience: str = "lung-app"
    access_ttl_s: int = 15 * 60
    refresh_ttl_days: int = 30
    email_code_ttl_min: int = 15
    # OAuth client IDs whose Google ID tokens we accept (Android, iOS, web), comma-separated
    google_client_ids: Annotated[list[str], NoDecode] = Field(default_factory=list)

    # ---- email (Brevo); without a key, emails are logged instead of sent
    brevo_api_key: SecretStr | None = None
    brevo_base: str = "https://api.brevo.com"
    mail_from: str = "no-reply@example.com"
    mail_from_name: str = "Lung Exposure Tracker"

    # ---- push (Firebase Cloud Messaging HTTP v1); without credentials, pushes are logged
    fcm_project_id: str | None = None
    fcm_service_account_json: SecretStr | None = None  # the JSON key file's contents

    # ---- rate limits (requests per window, per key)
    rate_limit_per_user_per_min: int = 60
    rate_limit_auth_per_ip_per_min: int = 10
    rate_limit_login_fail_per_email_15min: int = 5

    @field_validator(
        "ors_api_key",
        "firms_map_key",
        "openaq_api_key",
        "cpcb_api_key",
        "sqs_endpoint_url",
        "local_tick_minutes",
        "brevo_api_key",
        "fcm_project_id",
        "fcm_service_account_json",
        mode="before",
    )
    @classmethod
    def _blank_is_none(cls, v: object) -> object:
        return None if v == "" else v

    @field_validator("jwt_secret", mode="before")
    @classmethod
    def _blank_secret_is_dev(cls, v: object) -> object:
        # A blank line in .env means "not set": the dev secret, which production rejects.
        return DEV_JWT_SECRET if v in ("", None) else v

    @field_validator("google_client_ids", "cors_origins", mode="before")
    @classmethod
    def _comma_list(cls, v: object) -> object:
        if isinstance(v, str) and not v.startswith("["):
            return [x.strip() for x in v.split(",") if x.strip()]
        return v

    @model_validator(mode="after")
    def _safe_in_production(self) -> "Settings":
        if self.is_production:
            secret = self.jwt_secret.get_secret_value()
            if secret == DEV_JWT_SECRET or len(secret) < 32:
                raise ValueError("JWT_SECRET must be set to a random value of 32+ characters")
        return self

    @property
    def is_production(self) -> bool:
        return self.env in ("demo", "scale")


@lru_cache
def get_settings() -> Settings:
    return Settings()
