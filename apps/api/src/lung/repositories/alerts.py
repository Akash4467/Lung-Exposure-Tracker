from datetime import date
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession


async def claim(s: AsyncSession, user_id: UUID, alert_type: str, day: date) -> bool:
    """True only the first time; a repeat (SQS redelivery) gets False and sends nothing."""
    row = await s.execute(
        text(
            "INSERT INTO alerts (user_id, type, date) VALUES (:u, :t, :d) "
            "ON CONFLICT DO NOTHING RETURNING 1"
        ),
        {"u": user_id, "t": alert_type, "d": day},
    )
    return row.scalar_one_or_none() is not None
