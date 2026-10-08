from uuid import UUID

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession


async def for_user(s: AsyncSession, user_id: UUID) -> list[str]:
    rows = await s.execute(
        text("SELECT fcm_token FROM device_tokens WHERE user_id = :u"), {"u": user_id}
    )
    return list(rows.scalars().all())


async def upsert(s: AsyncSession, user_id: UUID, token: str, platform: str) -> None:
    await s.execute(
        text(
            """
            INSERT INTO device_tokens (user_id, fcm_token, platform) VALUES (:u, :t, :p)
            ON CONFLICT (fcm_token) DO UPDATE SET user_id = EXCLUDED.user_id,
              platform = EXCLUDED.platform, last_seen = now()
            """
        ),
        {"u": user_id, "t": token, "p": platform},
    )


async def owner(s: AsyncSession, token: str) -> UUID | None:
    r = await s.execute(
        text("SELECT user_id FROM device_tokens WHERE fcm_token = :t"), {"t": token}
    )
    return r.scalar_one_or_none()


async def delete(s: AsyncSession, token: str) -> None:
    """Drop a token FCM says is no longer valid."""
    await s.execute(text("DELETE FROM device_tokens WHERE fcm_token = :t"), {"t": token})
