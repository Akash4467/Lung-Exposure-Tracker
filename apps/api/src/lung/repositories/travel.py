import json
from dataclasses import dataclass, field
from datetime import datetime
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

RETENTION_DAYS = 7


@dataclass(frozen=True)
class LegRow:
    start_at: datetime
    end_at: datetime
    mode: str
    cell_id: str
    distance_m: float = 0.0
    path: list[list[float]] = field(default_factory=list)  # [[lat, lon], ...], simplified
    source: str = "gps"
    id: int | None = None


async def add_many(s: AsyncSession, user_id: UUID, legs: list[LegRow]) -> int:
    for leg in legs:
        await s.execute(
            text(
                "INSERT INTO travel_legs "
                "(user_id, start_at, end_at, mode, cell_id, distance_m, path, source) "
                "VALUES (:u, :start, :end, :mode, :cell, :dist, CAST(:path AS jsonb), :src)"
            ),
            {
                "u": user_id,
                "start": leg.start_at,
                "end": leg.end_at,
                "mode": leg.mode,
                "cell": leg.cell_id,
                "dist": leg.distance_m,
                "path": json.dumps(leg.path),
                "src": leg.source,
            },
        )
    return len(legs)


async def between(s: AsyncSession, user_id: UUID, start: datetime, end: datetime) -> list[LegRow]:
    rows = await s.execute(
        text(
            "SELECT id, start_at, end_at, mode, cell_id, distance_m, path, source "
            "FROM travel_legs WHERE user_id = :u AND end_at > :start AND start_at < :end "
            "ORDER BY start_at"
        ),
        {"u": user_id, "start": start, "end": end},
    )
    return [LegRow(**r) for r in rows.mappings().all()]


async def delete_all(s: AsyncSession, user_id: UUID) -> int:
    row = await s.execute(text("DELETE FROM travel_legs WHERE user_id = :u"), {"u": user_id})
    return int(row.rowcount)  # type: ignore[attr-defined]


async def purge_old(s: AsyncSession, now: datetime) -> int:
    """`now` is the app clock, so tests with a fixed clock keep their legs."""
    row = await s.execute(
        text(
            "DELETE FROM travel_legs "
            "WHERE start_at < CAST(:now AS timestamptz) - make_interval(days => :d)"
        ),
        {"d": RETENTION_DAYS, "now": now},
    )
    return int(row.rowcount)  # type: ignore[attr-defined]
