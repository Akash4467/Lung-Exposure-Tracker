from datetime import datetime

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from lung.integrations.firms import FireDetection


async def add_many(s: AsyncSession, fires: list[FireDetection]) -> int:
    for f in fires:
        await s.execute(
            text(
                """
                INSERT INTO fire_events (geo, detected_at, confidence, fire_power)
                VALUES (ST_SetSRID(ST_MakePoint(:lon, :lat), 4326)::geography, :at, :conf, :frp)
                ON CONFLICT (geo, detected_at) DO NOTHING
                """
            ),
            {"lon": f.lon, "lat": f.lat, "at": f.detected_at, "conf": f.confidence, "frp": f.frp},
        )
    return len(fires)


async def count_upwind(
    s: AsyncSession,
    lat: float,
    lon: float,
    radius_km: float,
    since: datetime,
    wind_from_deg: float,
    half_angle_deg: float,
) -> int:
    """Fires within `radius_km` whose direction from the point is within ±half_angle of where
    the wind comes from (meteorological convention). Low-confidence detections are ignored."""
    row = await s.execute(
        text(
            """
            WITH p AS (SELECT ST_SetSRID(ST_MakePoint(:lon, :lat), 4326)::geography AS g)
            SELECT count(*) FROM fire_events f, p
            WHERE f.detected_at >= :since
              AND coalesce(f.confidence, 'nominal') <> 'low'
              AND ST_DWithin(f.geo, p.g, :radius_m)
              AND abs(
                    mod(
                      (degrees(ST_Azimuth(p.g::geometry, f.geo::geometry)) - :wind + 540)::numeric,
                      360
                    ) - 180
                  ) <= :half
            """
        ),
        {
            "lon": lon,
            "lat": lat,
            "since": since,
            "radius_m": radius_km * 1000,
            "wind": wind_from_deg,
            "half": half_angle_deg,
        },
    )
    return int(row.scalar_one())


async def purge_before(s: AsyncSession, before: datetime) -> int:
    row = await s.execute(text("DELETE FROM fire_events WHERE detected_at < :b"), {"b": before})
    return int(row.rowcount)  # type: ignore[attr-defined]
