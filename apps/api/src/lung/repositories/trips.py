from dataclasses import dataclass
from datetime import date
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession


@dataclass(frozen=True)
class TripRow:
    label: str
    lat: float
    lon: float
    cell_id: str
    start_date: date
    end_date: date  # inclusive
    id: int | None = None

    def covers(self, day: date) -> bool:
        return self.start_date <= day <= self.end_date


COLUMNS = "id, label, lat, lon, cell_id, start_date, end_date"


async def ending_from(s: AsyncSession, user_id: UUID, day: date) -> list[TripRow]:
    """Trips that haven't finished before `day`, soonest first."""
    rows = await s.execute(
        text(
            f"SELECT {COLUMNS} FROM trips "  # noqa: S608
            "WHERE user_id = :u AND end_date >= :d ORDER BY start_date, id"
        ),
        {"u": user_id, "d": day},
    )
    return [TripRow(**r) for r in rows.mappings().all()]


async def add(s: AsyncSession, user_id: UUID, t: TripRow) -> int:
    row = await s.execute(
        text(
            "INSERT INTO trips (user_id, label, lat, lon, cell_id, start_date, end_date) "
            "VALUES (:u, :label, :lat, :lon, :cell, :start, :end) RETURNING id"
        ),
        {
            "u": user_id,
            "label": t.label,
            "lat": t.lat,
            "lon": t.lon,
            "cell": t.cell_id,
            "start": t.start_date,
            "end": t.end_date,
        },
    )
    return int(row.scalar_one())


async def delete(s: AsyncSession, user_id: UUID, trip_id: int) -> bool:
    row = await s.execute(
        text("DELETE FROM trips WHERE user_id = :u AND id = :id"), {"u": user_id, "id": trip_id}
    )
    return bool(row.rowcount)  # type: ignore[attr-defined]


async def set_end(s: AsyncSession, user_id: UUID, trip_id: int, end: date) -> None:
    await s.execute(
        text("UPDATE trips SET end_date = :e WHERE user_id = :u AND id = :id"),
        {"u": user_id, "id": trip_id, "e": end},
    )
