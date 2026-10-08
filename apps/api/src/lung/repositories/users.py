from uuid import UUID

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession


async def create(s: AsyncSession, user_id: UUID | None = None) -> UUID:
    if user_id is None:
        row = await s.execute(text("INSERT INTO users DEFAULT VALUES RETURNING id"))
    else:
        row = await s.execute(
            text("INSERT INTO users (id) VALUES (:id) ON CONFLICT DO NOTHING RETURNING id"),
            {"id": user_id},
        )
    found = row.scalar_one_or_none()
    return found if found is not None else user_id  # type: ignore[return-value]


async def exists(s: AsyncSession, user_id: UUID) -> bool:
    row = await s.execute(text("SELECT 1 FROM users WHERE id = :id"), {"id": user_id})
    return row.scalar_one_or_none() is not None


async def delete(s: AsyncSession, user_id: UUID) -> None:
    """Every user-owned row goes with it (ON DELETE CASCADE)."""
    await s.execute(text("DELETE FROM users WHERE id = :id"), {"id": user_id})
