from dataclasses import dataclass
from datetime import datetime
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession


@dataclass(frozen=True)
class ActivityRow:
    start_at: datetime
    end_at: datetime
    kind: str  # asleep | light | walk | run | cycle
    met: float | None = None
    outdoors: bool | None = None
    source: str = "manual"  # manual | activity_recognition | health_connect
    heart_rate: float | None = None
    steps_per_min: float | None = None
    id: int | None = None


COLUMNS = "start_at, end_at, kind, met, outdoors, source, heart_rate, steps_per_min"


async def between(
    s: AsyncSession, user_id: UUID, start: datetime, end: datetime
) -> list[ActivityRow]:
    rows = await s.execute(
        text(
            f"SELECT id, {COLUMNS} FROM activity_intervals "  # noqa: S608
            "WHERE user_id = :u AND end_at > :start AND start_at < :end "
            "ORDER BY start_at, id"
        ),
        {"u": user_id, "start": start, "end": end},
    )
    return [ActivityRow(**r) for r in rows.mappings().all()]


async def add_many(s: AsyncSession, user_id: UUID, items: list[ActivityRow]) -> list[int]:
    ids: list[int] = []
    for a in items:
        values = {k: v for k, v in a.__dict__.items() if k != "id"}
        row = await s.execute(
            text(
                f"INSERT INTO activity_intervals (user_id, {COLUMNS}) VALUES "  # noqa: S608
                "(:u, :start_at, :end_at, :kind, :met, :outdoors, :source, :heart_rate, "
                ":steps_per_min) RETURNING id"
            ),
            {"u": user_id, **values},
        )
        ids.append(row.scalar_one())
    return ids


async def delete(s: AsyncSession, user_id: UUID, activity_id: int) -> bool:
    row = await s.execute(
        text("DELETE FROM activity_intervals WHERE user_id = :u AND id = :id"),
        {"u": user_id, "id": activity_id},
    )
    return bool(row.rowcount)  # type: ignore[attr-defined]


async def delete_source_between(
    s: AsyncSession, user_id: UUID, source: str, start: datetime, end: datetime
) -> int:
    row = await s.execute(
        text(
            "DELETE FROM activity_intervals WHERE user_id = :u AND source = :src "
            "AND start_at >= :start AND end_at <= :end"
        ),
        {"u": user_id, "src": source, "start": start, "end": end},
    )
    return int(row.rowcount)  # type: ignore[attr-defined]
