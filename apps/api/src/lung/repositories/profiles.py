from dataclasses import dataclass
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession


@dataclass(frozen=True)
class ProfileRow:
    user_id: UUID
    age: int
    sex: str
    sensitive: bool
    weight_kg: float | None
    timezone: str


async def get(s: AsyncSession, user_id: UUID) -> ProfileRow | None:
    row = await s.execute(
        text(
            "SELECT user_id, age, sex, sensitive, weight_kg, timezone "
            "FROM profiles WHERE user_id = :id"
        ),
        {"id": user_id},
    )
    r = row.mappings().one_or_none()
    return ProfileRow(**r) if r else None


async def upsert(s: AsyncSession, p: ProfileRow) -> None:
    await s.execute(
        text(
            """
            INSERT INTO profiles (user_id, age, sex, sensitive, weight_kg, timezone)
            VALUES (:user_id, :age, :sex, :sensitive, :weight_kg, :timezone)
            ON CONFLICT (user_id) DO UPDATE SET
              age = EXCLUDED.age, sex = EXCLUDED.sex, sensitive = EXCLUDED.sensitive,
              weight_kg = EXCLUDED.weight_kg, timezone = EXCLUDED.timezone, updated_at = now()
            """
        ),
        p.__dict__,
    )
