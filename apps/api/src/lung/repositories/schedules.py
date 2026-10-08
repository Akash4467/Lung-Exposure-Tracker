from dataclasses import dataclass
from datetime import time
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession


@dataclass(frozen=True)
class ScheduleRow:
    wake: time
    leave_home: time
    arrive_office: time
    leave_office: time
    arrive_home: time
    sleep: time
    commute_mode: str
    commute_mask: str = "none"
    office_days: tuple[int, ...] = (1, 2, 3, 4, 5)  # ISO weekdays


COLUMNS = (
    "wake, leave_home, arrive_office, leave_office, arrive_home, sleep, "
    "commute_mode, commute_mask, office_days"
)


async def get(s: AsyncSession, user_id: UUID) -> ScheduleRow | None:
    row = await s.execute(
        text(f"SELECT {COLUMNS} FROM schedules WHERE user_id = :u"),  # noqa: S608
        {"u": user_id},
    )
    r = row.mappings().one_or_none()
    if r is None:
        return None
    return ScheduleRow(**{**r, "office_days": tuple(r["office_days"])})


async def upsert(s: AsyncSession, user_id: UUID, sc: ScheduleRow) -> None:
    await s.execute(
        text(
            f"""
            INSERT INTO schedules (user_id, {COLUMNS})
            VALUES (:u, :wake, :leave_home, :arrive_office, :leave_office, :arrive_home,
                    :sleep, :commute_mode, :commute_mask, :office_days)
            ON CONFLICT (user_id) DO UPDATE SET
              wake = EXCLUDED.wake, leave_home = EXCLUDED.leave_home,
              arrive_office = EXCLUDED.arrive_office, leave_office = EXCLUDED.leave_office,
              arrive_home = EXCLUDED.arrive_home, sleep = EXCLUDED.sleep,
              commute_mode = EXCLUDED.commute_mode, commute_mask = EXCLUDED.commute_mask,
              office_days = EXCLUDED.office_days
            """  # noqa: S608
        ),
        {"u": user_id, **sc.__dict__, "office_days": list(sc.office_days)},
    )
