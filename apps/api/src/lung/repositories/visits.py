from dataclasses import dataclass
from datetime import datetime
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession


@dataclass(frozen=True)
class VisitRow:
    place: str  # home | office | away
    start_at: datetime
    end_at: datetime
    activity: str | None = None


async def between(s: AsyncSession, user_id: UUID, start: datetime, end: datetime) -> list[VisitRow]:
    rows = await s.execute(
        text(
            """
            SELECT place, start_at, end_at, activity FROM visits
            WHERE user_id = :u AND end_at > :start AND start_at < :end
            ORDER BY start_at
            """
        ),
        {"u": user_id, "start": start, "end": end},
    )
    return [VisitRow(**r) for r in rows.mappings().all()]


async def add_many(s: AsyncSession, user_id: UUID, visits: list[VisitRow]) -> None:
    for v in visits:
        await s.execute(
            text(
                "INSERT INTO visits (user_id, place, start_at, end_at, activity) "
                "VALUES (:u, :place, :start_at, :end_at, :activity)"
            ),
            {"u": user_id, **v.__dict__},
        )
