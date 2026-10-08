from dataclasses import dataclass
from datetime import datetime
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession


@dataclass(frozen=True)
class RefreshRow:
    id: UUID
    user_id: UUID
    family_id: UUID
    expires_at: datetime
    used_at: datetime | None
    revoked_at: datetime | None


async def add(
    s: AsyncSession, user_id: UUID, family_id: UUID, token_hash: bytes, expires_at: datetime
) -> None:
    await s.execute(
        text(
            "INSERT INTO refresh_tokens (user_id, family_id, token_hash, expires_at) "
            "VALUES (:u, :f, :h, :e)"
        ),
        {"u": user_id, "f": family_id, "h": token_hash, "e": expires_at},
    )


async def by_hash_for_update(s: AsyncSession, token_hash: bytes) -> RefreshRow | None:
    """Row-locked, so two refreshes racing with the same token can't both succeed."""
    r = await s.execute(
        text(
            "SELECT id, user_id, family_id, expires_at, used_at, revoked_at "
            "FROM refresh_tokens WHERE token_hash = :h FOR UPDATE"
        ),
        {"h": token_hash},
    )
    m = r.mappings().one_or_none()
    return RefreshRow(**m) if m else None


async def mark_used(s: AsyncSession, token_id: UUID) -> None:
    await s.execute(
        text("UPDATE refresh_tokens SET used_at = now() WHERE id = :id"), {"id": token_id}
    )


async def revoke_family(s: AsyncSession, family_id: UUID) -> None:
    await s.execute(
        text(
            "UPDATE refresh_tokens SET revoked_at = now() "
            "WHERE family_id = :f AND revoked_at IS NULL"
        ),
        {"f": family_id},
    )


async def revoke_all(s: AsyncSession, user_id: UUID) -> None:
    await s.execute(
        text(
            "UPDATE refresh_tokens SET revoked_at = now() WHERE user_id = :u AND revoked_at IS NULL"
        ),
        {"u": user_id},
    )


async def purge_expired(s: AsyncSession) -> int:
    r = await s.execute(
        text("DELETE FROM refresh_tokens WHERE expires_at < now() - interval '7 days'")
    )
    return r.rowcount  # type: ignore[attr-defined, no-any-return]
