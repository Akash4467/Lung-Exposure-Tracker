from dataclasses import dataclass, field
from datetime import time
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession


@dataclass(frozen=True)
class SourceRow:
    kind: str
    start_time: time
    minutes: int


@dataclass(frozen=True)
class PlaceRow:
    type: str  # home | office
    label: str | None
    lat: float
    lon: float
    cell_id: str
    windows: str = "normal"
    purifier: bool = False
    purifier_cadr_m3h: float | None = None
    size: str | None = None
    sources: tuple[SourceRow, ...] = field(default=())
    id: UUID | None = None


async def for_user(s: AsyncSession, user_id: UUID) -> dict[str, PlaceRow]:
    rows = (
        (
            await s.execute(
                text(
                    """
                SELECT id, type, label, ST_Y(geo::geometry) AS lat, ST_X(geo::geometry) AS lon,
                       cell_id, windows, purifier, purifier_cadr_m3h, size
                FROM places WHERE user_id = :u
                """
                ),
                {"u": user_id},
            )
        )
        .mappings()
        .all()
    )
    src = (
        (
            await s.execute(
                text(
                    """
                SELECT place_id, kind, start_time, minutes FROM indoor_sources
                WHERE place_id IN (SELECT id FROM places WHERE user_id = :u)
                ORDER BY start_time
                """
                ),
                {"u": user_id},
            )
        )
        .mappings()
        .all()
    )
    by_place: dict[UUID, list[SourceRow]] = {}
    for r in src:
        by_place.setdefault(r["place_id"], []).append(
            SourceRow(r["kind"], r["start_time"], r["minutes"])
        )
    return {r["type"]: PlaceRow(**r, sources=tuple(by_place.get(r["id"], []))) for r in rows}


async def upsert(s: AsyncSession, user_id: UUID, p: PlaceRow) -> UUID:
    """Saves location and indoor details, and replaces the place's indoor sources."""
    place_id = (
        await s.execute(
            text(
                """
                INSERT INTO places (user_id, type, label, geo, cell_id,
                                    windows, purifier, purifier_cadr_m3h, size)
                VALUES (:u, :type, :label,
                        ST_SetSRID(ST_MakePoint(:lon, :lat), 4326)::geography, :cell_id,
                        :windows, :purifier, :cadr, :size)
                ON CONFLICT (user_id, type) DO UPDATE SET
                  label = EXCLUDED.label, geo = EXCLUDED.geo, cell_id = EXCLUDED.cell_id,
                  windows = EXCLUDED.windows, purifier = EXCLUDED.purifier,
                  purifier_cadr_m3h = EXCLUDED.purifier_cadr_m3h, size = EXCLUDED.size,
                  updated_at = now()
                RETURNING id
                """
            ),
            {
                "u": user_id,
                "type": p.type,
                "label": p.label,
                "lat": p.lat,
                "lon": p.lon,
                "cell_id": p.cell_id,
                "windows": p.windows,
                "purifier": p.purifier,
                "cadr": p.purifier_cadr_m3h,
                "size": p.size,
            },
        )
    ).scalar_one()
    await s.execute(text("DELETE FROM indoor_sources WHERE place_id = :p"), {"p": place_id})
    for src in p.sources:
        await s.execute(
            text(
                "INSERT INTO indoor_sources (place_id, kind, start_time, minutes) "
                "VALUES (:p, :kind, :start, :minutes)"
            ),
            {"p": place_id, "kind": src.kind, "start": src.start_time, "minutes": src.minutes},
        )
    return place_id  # type: ignore[no-any-return]


async def set_indoor(
    s: AsyncSession, user_id: UUID, place_type: str, windows: str, purifier: bool
) -> bool:
    row = await s.execute(
        text(
            "UPDATE places SET windows = :w, purifier = :p, updated_at = now() "
            "WHERE user_id = :u AND type = :t RETURNING id"
        ),
        {"w": windows, "p": purifier, "u": user_id, "t": place_type},
    )
    return row.scalar_one_or_none() is not None


async def cells_in_use(s: AsyncSession) -> list[str]:
    """Every cell someone needs air for: their places, their route, and the destinations of
    trips that are on now or start within the next 3 days (so the air is there in time)."""
    rows = await s.execute(
        text(
            "SELECT cell_id FROM places UNION SELECT cell_id FROM route_points "
            "UNION SELECT cell_id FROM trips "
            "WHERE end_date >= CURRENT_DATE - 1 AND start_date <= CURRENT_DATE + 3 "
            "UNION SELECT cell_id FROM travel_legs WHERE start_at > now() - interval '2 days' "
            "ORDER BY 1"
        )
    )
    return list(rows.scalars().all())


async def users_in_cell(s: AsyncSession, cell_id: str) -> list[UUID]:
    rows = await s.execute(
        text(
            "SELECT user_id FROM places WHERE cell_id = :c "
            "UNION SELECT user_id FROM route_points WHERE cell_id = :c "
            "UNION SELECT user_id FROM trips WHERE cell_id = :c "
            "AND end_date >= CURRENT_DATE - 1 AND start_date <= CURRENT_DATE + 3 "
            "UNION SELECT user_id FROM travel_legs WHERE cell_id = :c "
            "AND start_at > now() - interval '2 days'"
        ),
        {"c": cell_id},
    )
    return list(rows.scalars().all())
