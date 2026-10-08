from collections.abc import Sequence
from datetime import datetime
from typing import Any

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from lung.domain.air import HourlyAir


async def ensure_partitions(s: AsyncSession, months_ahead: int = 2) -> None:
    await s.execute(text("SELECT ensure_air_partitions(:m)"), {"m": months_ahead})


async def upsert_many(s: AsyncSession, cell_id: str, source: str, rows: Sequence[HourlyAir]) -> int:
    """Insert or overwrite each (cell, hour). Running it twice changes nothing."""
    if not rows:
        return 0
    await s.execute(
        text(
            """
            INSERT INTO air_readings (cell_id, hour, pm25, pm10, wind_speed, wind_dir, source)
            VALUES (:cell, :hour, :pm25, :pm10, :wind_speed, :wind_dir, :source)
            ON CONFLICT (cell_id, hour) DO UPDATE SET
              pm25 = EXCLUDED.pm25, pm10 = EXCLUDED.pm10, wind_speed = EXCLUDED.wind_speed,
              wind_dir = EXCLUDED.wind_dir, source = EXCLUDED.source, fetched_at = now()
            """
        ),
        [
            {
                "cell": cell_id,
                "hour": r.hour,
                "pm25": r.pm25,
                "pm10": r.pm10,
                "wind_speed": r.wind_speed,
                "wind_dir": r.wind_dir,
                "source": source,
            }
            for r in rows
        ],
    )
    return len(rows)


async def pm25_for(
    s: AsyncSession, cells: Sequence[str], start: datetime, end: datetime
) -> dict[str, dict[datetime, float]]:
    rows = await s.execute(
        text(
            "SELECT cell_id, hour, pm25 FROM air_readings "
            "WHERE cell_id = ANY(:cells) AND hour >= :start AND hour < :end"
        ),
        {"cells": list(cells), "start": start, "end": end},
    )
    out: dict[str, dict[datetime, float]] = {c: {} for c in cells}
    for cell, hour, pm25 in rows.all():
        out[cell][hour] = pm25
    return out


async def latest_fetch(s: AsyncSession, cells: Sequence[str]) -> datetime | None:
    row = await s.execute(
        text("SELECT max(fetched_at) FROM air_readings WHERE cell_id = ANY(:cells)"),
        {"cells": list(cells)},
    )
    return row.scalar_one_or_none()


async def hourly_for_point(
    s: AsyncSession, cell_id: str, start: datetime, end: datetime
) -> list[dict[str, Any]]:
    rows = await s.execute(
        text(
            "SELECT hour, pm25, pm10, wind_speed, wind_dir, source FROM air_readings "
            "WHERE cell_id = :c AND hour >= :start AND hour < :end ORDER BY hour"
        ),
        {"c": cell_id, "start": start, "end": end},
    )
    return [dict(r) for r in rows.mappings().all()]


async def has_source(
    s: AsyncSession, cell_id: str, start: datetime, end: datetime, source: str
) -> bool:
    row = await s.execute(
        text(
            "SELECT EXISTS (SELECT 1 FROM air_readings WHERE cell_id = :c "
            "AND hour >= :start AND hour < :end AND source = :src)"
        ),
        {"c": cell_id, "start": start, "end": end, "src": source},
    )
    return bool(row.scalar_one())
