from datetime import datetime
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

MAX_ATTEMPTS = 5


async def put(
    s: AsyncSession, user_id: UUID, purpose: str, code_hash: bytes, expires_at: datetime
) -> None:
    """A new code replaces any earlier one for the same purpose and resets the attempts."""
    await s.execute(
        text(
            """
            INSERT INTO email_codes (user_id, purpose, code_hash, expires_at)
            VALUES (:u, :p, :h, :e)
            ON CONFLICT (user_id, purpose) DO UPDATE SET
              code_hash = EXCLUDED.code_hash, expires_at = EXCLUDED.expires_at,
              attempts = 0, created_at = now()
            """
        ),
        {"u": user_id, "p": purpose, "h": code_hash, "e": expires_at},
    )


async def consume(
    s: AsyncSession, user_id: UUID, purpose: str, code_hash: bytes, now: datetime
) -> bool:
    """True if the code matches and is still valid; it's then deleted. A wrong guess counts
    as an attempt, and after MAX_ATTEMPTS the code is dead even if the right one comes later."""
    r = await s.execute(
        text(
            "SELECT code_hash, attempts, expires_at > :now AS live FROM email_codes "
            "WHERE user_id = :u AND purpose = :p FOR UPDATE"
        ),
        {"u": user_id, "p": purpose, "now": now},
    )
    row = r.mappings().one_or_none()
    if row is None or not row["live"] or row["attempts"] >= MAX_ATTEMPTS:
        return False
    if bytes(row["code_hash"]) != code_hash:
        await s.execute(
            text(
                "UPDATE email_codes SET attempts = attempts + 1 WHERE user_id = :u AND purpose = :p"
            ),
            {"u": user_id, "p": purpose},
        )
        return False
    await s.execute(
        text("DELETE FROM email_codes WHERE user_id = :u AND purpose = :p"),
        {"u": user_id, "p": purpose},
    )
    return True
