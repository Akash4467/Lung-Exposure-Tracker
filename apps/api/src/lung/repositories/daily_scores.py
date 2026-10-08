import json
from dataclasses import asdict, dataclass, field
from datetime import date, datetime
from typing import Any
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession


@dataclass(frozen=True)
class ScoreRow:
    date: date
    is_forecast: bool
    dose_ug: float
    score: float
    score_p10: float
    score_p90: float
    band: str
    cigarettes: float
    avg_pm25: float
    home_share: float
    commute_share: float
    office_share: float
    indoor_source_share: float
    fire_risk: str | None
    data_as_of: datetime
    engine_version: str
    details: dict[str, Any] = field(default_factory=dict)
    computed_at: datetime | None = None


FIELDS = [
    "date",
    "is_forecast",
    "dose_ug",
    "score",
    "score_p10",
    "score_p90",
    "band",
    "cigarettes",
    "avg_pm25",
    "home_share",
    "commute_share",
    "office_share",
    "indoor_source_share",
    "fire_risk",
    "data_as_of",
    "engine_version",
    "details",
]


async def upsert(s: AsyncSession, user_id: UUID, row: ScoreRow) -> None:
    values = {k: v for k, v in asdict(row).items() if k in FIELDS}
    values["details"] = json.dumps(row.details, default=str)
    cols = ", ".join(FIELDS)
    params = ", ".join(f":{f}" for f in FIELDS).replace(":details", "CAST(:details AS jsonb)")
    updates = ", ".join(f"{f} = EXCLUDED.{f}" for f in FIELDS if f not in ("date", "is_forecast"))
    await s.execute(
        text(
            f"INSERT INTO daily_scores (user_id, {cols}) VALUES (:u, {params}) "  # noqa: S608
            f"ON CONFLICT (user_id, date, is_forecast) DO UPDATE SET {updates}, "
            "computed_at = now()"
        ),
        {"u": user_id, **values},
    )


async def get(s: AsyncSession, user_id: UUID, day: date, is_forecast: bool) -> ScoreRow | None:
    row = await s.execute(
        text(
            f"SELECT {', '.join(FIELDS)}, computed_at FROM daily_scores "  # noqa: S608
            "WHERE user_id = :u AND date = :d AND is_forecast = :f"
        ),
        {"u": user_id, "d": day, "f": is_forecast},
    )
    r = row.mappings().one_or_none()
    return ScoreRow(**r) if r else None


async def between(s: AsyncSession, user_id: UUID, first: date, last: date) -> list[ScoreRow]:
    """Stored past/present days (not forecasts), oldest first."""
    rows = await s.execute(
        text(
            f"SELECT {', '.join(FIELDS)}, computed_at FROM daily_scores "  # noqa: S608
            "WHERE user_id = :u AND NOT is_forecast AND date BETWEEN :a AND :b ORDER BY date"
        ),
        {"u": user_id, "a": first, "b": last},
    )
    return [ScoreRow(**r) for r in rows.mappings().all()]
