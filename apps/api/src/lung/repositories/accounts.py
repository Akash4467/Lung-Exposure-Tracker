"""The auth side of `users`: email, password hash, Google subject."""

from dataclasses import dataclass
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession


@dataclass(frozen=True)
class AccountRow:
    id: UUID
    email: str | None
    email_verified: bool
    password_hash: str | None
    google_sub: str | None


COLS = "id, email, email_verified, password_hash, google_sub"


async def by_email(s: AsyncSession, email: str) -> AccountRow | None:
    r = await s.execute(text(f"SELECT {COLS} FROM users WHERE email = :e"), {"e": email})  # noqa: S608
    m = r.mappings().one_or_none()
    return AccountRow(**m) if m else None


async def by_id(s: AsyncSession, user_id: UUID) -> AccountRow | None:
    r = await s.execute(text(f"SELECT {COLS} FROM users WHERE id = :id"), {"id": user_id})  # noqa: S608
    m = r.mappings().one_or_none()
    return AccountRow(**m) if m else None


async def by_google_sub(s: AsyncSession, sub: str) -> AccountRow | None:
    r = await s.execute(text(f"SELECT {COLS} FROM users WHERE google_sub = :g"), {"g": sub})  # noqa: S608
    m = r.mappings().one_or_none()
    return AccountRow(**m) if m else None


async def create(
    s: AsyncSession,
    email: str,
    password_hash: str | None,
    email_verified: bool = False,
    google_sub: str | None = None,
) -> UUID:
    r = await s.execute(
        text(
            "INSERT INTO users (email, password_hash, email_verified, google_sub) "
            "VALUES (:e, :p, :v, :g) RETURNING id"
        ),
        {"e": email, "p": password_hash, "v": email_verified, "g": google_sub},
    )
    return r.scalar_one()  # type: ignore[no-any-return]


async def link_google(s: AsyncSession, user_id: UUID, sub: str, drop_password: bool) -> None:
    """Attach a Google identity. If the email was never verified, whoever set that password
    never proved they own the address, so the password is removed."""
    await s.execute(
        text(
            "UPDATE users SET google_sub = :g, email_verified = true, "
            "password_hash = CASE WHEN :drop THEN NULL ELSE password_hash END WHERE id = :id"
        ),
        {"g": sub, "drop": drop_password, "id": user_id},
    )


async def set_password(s: AsyncSession, user_id: UUID, password_hash: str) -> None:
    await s.execute(
        text("UPDATE users SET password_hash = :p WHERE id = :id"),
        {"p": password_hash, "id": user_id},
    )


async def mark_verified(s: AsyncSession, user_id: UUID) -> None:
    await s.execute(text("UPDATE users SET email_verified = true WHERE id = :id"), {"id": user_id})


async def touch_login(s: AsyncSession, user_id: UUID) -> None:
    await s.execute(text("UPDATE users SET last_login_at = now() WHERE id = :id"), {"id": user_id})
