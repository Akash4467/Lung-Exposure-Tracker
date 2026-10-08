"""Core schema: users, profile, places, schedule, routes, visits, scores, air and fires.

Revision ID: 0001
Revises:
Create Date: 2026-10-04
"""

from collections.abc import Sequence

from alembic import op

revision: str = "0001"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

UP = [
    "CREATE EXTENSION IF NOT EXISTS postgis",
    "CREATE EXTENSION IF NOT EXISTS citext",
    # ---------------------------------------------------------------- user-owned
    # Identity only; auth columns are added in the auth migration.
    """
    CREATE TABLE users (
      id          uuid PRIMARY KEY DEFAULT gen_random_uuid(),
      created_at  timestamptz NOT NULL DEFAULT now()
    )
    """,
    """
    CREATE TABLE profiles (
      user_id     uuid PRIMARY KEY REFERENCES users(id) ON DELETE CASCADE,
      age         smallint NOT NULL CHECK (age BETWEEN 3 AND 110),
      sex         text NOT NULL CHECK (sex IN ('man','woman','other')),
      sensitive   boolean NOT NULL DEFAULT false,
      weight_kg   real CHECK (weight_kg BETWEEN 10 AND 300),
      timezone    text NOT NULL DEFAULT 'Asia/Kolkata',
      updated_at  timestamptz NOT NULL DEFAULT now()
    )
    """,
    """
    CREATE TABLE places (
      id                 uuid PRIMARY KEY DEFAULT gen_random_uuid(),
      user_id            uuid NOT NULL REFERENCES users(id) ON DELETE CASCADE,
      type               text NOT NULL CHECK (type IN ('home','office')),
      label              text,
      geo                geography(Point,4326) NOT NULL,
      cell_id            text NOT NULL,
      windows            text NOT NULL DEFAULT 'normal'
                         CHECK (windows IN ('closed','normal','open')),
      purifier           boolean NOT NULL DEFAULT false,
      purifier_cadr_m3h  real CHECK (purifier_cadr_m3h > 0),
      size               text,
      updated_at         timestamptz NOT NULL DEFAULT now(),
      UNIQUE (user_id, type)
    )
    """,
    "CREATE INDEX places_cell ON places (cell_id)",
    """
    CREATE TABLE indoor_sources (
      id          uuid PRIMARY KEY DEFAULT gen_random_uuid(),
      place_id    uuid NOT NULL REFERENCES places(id) ON DELETE CASCADE,
      kind        text NOT NULL,
      start_time  time NOT NULL,
      minutes     smallint NOT NULL CHECK (minutes BETWEEN 1 AND 1440)
    )
    """,
    "CREATE INDEX indoor_sources_place ON indoor_sources (place_id)",
    """
    CREATE TABLE schedules (
      user_id        uuid PRIMARY KEY REFERENCES users(id) ON DELETE CASCADE,
      wake           time NOT NULL,
      leave_home     time NOT NULL,
      arrive_office  time NOT NULL,
      leave_office   time NOT NULL,
      arrive_home    time NOT NULL,
      sleep          time NOT NULL,
      commute_mode   text NOT NULL
                     CHECK (commute_mode IN ('walk','cycle','bus_metro','two_wheeler','car')),
      commute_mask   text NOT NULL DEFAULT 'none'
                     CHECK (commute_mask IN ('none','cloth','surgical','n95')),
      office_days    smallint[] NOT NULL DEFAULT '{1,2,3,4,5}',   -- ISO weekdays
      CHECK (leave_home < arrive_office AND arrive_office < leave_office
             AND leave_office < arrive_home)
    )
    """,
    """
    CREATE TABLE routes (
      user_id      uuid PRIMARY KEY REFERENCES users(id) ON DELETE CASCADE,
      source       text NOT NULL CHECK (source IN ('openrouteservice','straight_line')),
      distance_km  real NOT NULL,
      computed_at  timestamptz NOT NULL DEFAULT now()
    )
    """,
    """
    CREATE TABLE route_points (
      user_id     uuid NOT NULL REFERENCES routes(user_id) ON DELETE CASCADE,
      seq         smallint NOT NULL,
      geo         geography(Point,4326) NOT NULL,
      cell_id     text NOT NULL,
      road_class  text NOT NULL DEFAULT 'unknown',
      PRIMARY KEY (user_id, seq)
    )
    """,
    "CREATE INDEX route_points_cell ON route_points (cell_id)",
    """
    CREATE TABLE visits (
      id        bigserial PRIMARY KEY,
      user_id   uuid NOT NULL REFERENCES users(id) ON DELETE CASCADE,
      place     text NOT NULL CHECK (place IN ('home','office','away')),
      start_at  timestamptz NOT NULL,
      end_at    timestamptz NOT NULL CHECK (end_at > start_at),
      activity  text CHECK (activity IN ('asleep','light','walk','cycle'))
    )
    """,
    "CREATE INDEX visits_user_time ON visits (user_id, start_at)",
    """
    CREATE TABLE daily_scores (
      user_id              uuid NOT NULL REFERENCES users(id) ON DELETE CASCADE,
      date                 date NOT NULL,
      is_forecast          boolean NOT NULL,
      dose_ug              real NOT NULL,
      score                real NOT NULL,
      score_p10            real NOT NULL,
      score_p90            real NOT NULL,
      band                 text NOT NULL CHECK (band IN ('green','amber','red')),
      cigarettes           real NOT NULL,
      avg_pm25             real NOT NULL,
      home_share           real NOT NULL,
      commute_share        real NOT NULL,
      office_share         real NOT NULL,
      indoor_source_share  real NOT NULL,
      fire_risk            text CHECK (fire_risk IN ('none','low','medium','high')),
      details              jsonb NOT NULL DEFAULT '{}',   -- tips, hours, band odds
      data_as_of           timestamptz NOT NULL,
      engine_version       text NOT NULL,
      computed_at          timestamptz NOT NULL DEFAULT now(),
      PRIMARY KEY (user_id, date, is_forecast)
    )
    """,
    """
    CREATE TABLE device_tokens (
      id          uuid PRIMARY KEY DEFAULT gen_random_uuid(),
      user_id     uuid NOT NULL REFERENCES users(id) ON DELETE CASCADE,
      fcm_token   text NOT NULL UNIQUE,
      platform    text NOT NULL CHECK (platform IN ('android','ios')),
      last_seen   timestamptz NOT NULL DEFAULT now()
    )
    """,
    """
    CREATE TABLE alerts (
      user_id  uuid NOT NULL REFERENCES users(id) ON DELETE CASCADE,
      type     text NOT NULL,
      date     date NOT NULL,
      sent_at  timestamptz NOT NULL DEFAULT now(),
      PRIMARY KEY (user_id, type, date)
    )
    """,
    # ---------------------------------------------------------------- shared
    """
    CREATE TABLE air_readings (
      cell_id     text        NOT NULL,
      hour        timestamptz NOT NULL,
      pm25        real        NOT NULL CHECK (pm25 >= 0),
      pm10        real,
      wind_speed  real,
      wind_dir    real,
      source      text        NOT NULL,
      fetched_at  timestamptz NOT NULL DEFAULT now(),
      PRIMARY KEY (cell_id, hour)
    ) PARTITION BY RANGE (hour)
    """,
    # Creates monthly partitions from this month to `months_ahead` months out. Idempotent.
    """
    CREATE FUNCTION ensure_air_partitions(months_ahead int) RETURNS void
    LANGUAGE plpgsql AS $$
    DECLARE
      m date := date_trunc('month', now() AT TIME ZONE 'UTC')::date - interval '1 month';
      i int;
    BEGIN
      FOR i IN 0..months_ahead + 1 LOOP
        EXECUTE format(
          'CREATE TABLE IF NOT EXISTS %I PARTITION OF air_readings
             FOR VALUES FROM (%L) TO (%L)',
          'air_readings_' || to_char(m, 'YYYY_MM'),
          m::timestamptz AT TIME ZONE 'UTC',
          (m + interval '1 month')::timestamptz AT TIME ZONE 'UTC');
        m := m + interval '1 month';
      END LOOP;
    END $$
    """,
    "SELECT ensure_air_partitions(2)",
    """
    CREATE TABLE fire_events (
      id           bigserial PRIMARY KEY,
      geo          geography(Point,4326) NOT NULL,
      detected_at  timestamptz NOT NULL,
      confidence   text,
      fire_power   real,
      UNIQUE (geo, detected_at)
    )
    """,
    "CREATE INDEX fire_events_geo ON fire_events USING gist (geo)",
    "CREATE INDEX fire_events_time ON fire_events (detected_at)",
]

DOWN = [
    "DROP TABLE IF EXISTS fire_events",
    "DROP FUNCTION IF EXISTS ensure_air_partitions(int)",
    "DROP TABLE IF EXISTS air_readings CASCADE",
    "DROP TABLE IF EXISTS alerts",
    "DROP TABLE IF EXISTS device_tokens",
    "DROP TABLE IF EXISTS daily_scores",
    "DROP TABLE IF EXISTS visits",
    "DROP TABLE IF EXISTS route_points",
    "DROP TABLE IF EXISTS routes",
    "DROP TABLE IF EXISTS schedules",
    "DROP TABLE IF EXISTS indoor_sources",
    "DROP TABLE IF EXISTS places",
    "DROP TABLE IF EXISTS profiles",
    "DROP TABLE IF EXISTS users",
]


def upgrade() -> None:
    for statement in UP:
        op.execute(statement)


def downgrade() -> None:
    for statement in DOWN:
        op.execute(statement)
