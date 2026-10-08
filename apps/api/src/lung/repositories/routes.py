from dataclasses import dataclass
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession


@dataclass(frozen=True)
class RoutePointRow:
    lat: float
    lon: float
    cell_id: str
    road_class: str


async def points(s: AsyncSession, user_id: UUID) -> list[RoutePointRow]:
    rows = await s.execute(
        text(
            """
            SELECT ST_Y(geo::geometry) AS lat, ST_X(geo::geometry) AS lon, cell_id, road_class
            FROM route_points WHERE user_id = :u ORDER BY seq
            """
        ),
        {"u": user_id},
    )
    return [RoutePointRow(**r) for r in rows.mappings().all()]


async def replace(
    s: AsyncSession, user_id: UUID, source: str, distance_km: float, pts: list[RoutePointRow]
) -> None:
    await s.execute(text("DELETE FROM routes WHERE user_id = :u"), {"u": user_id})
    await s.execute(
        text("INSERT INTO routes (user_id, source, distance_km) VALUES (:u, :s, :d)"),
        {"u": user_id, "s": source, "d": distance_km},
    )
    for seq, p in enumerate(pts):
        await s.execute(
            text(
                """
                INSERT INTO route_points (user_id, seq, geo, cell_id, road_class)
                VALUES (:u, :seq, ST_SetSRID(ST_MakePoint(:lon, :lat), 4326)::geography,
                        :cell, :road)
                """
            ),
            {
                "u": user_id,
                "seq": seq,
                "lon": p.lon,
                "lat": p.lat,
                "cell": p.cell_id,
                "road": p.road_class,
            },
        )


async def meta(s: AsyncSession, user_id: UUID) -> tuple[str, float] | None:
    """(source, distance_km) of the stored route, or None."""
    row = await s.execute(
        text("SELECT source, distance_km FROM routes WHERE user_id = :u"), {"u": user_id}
    )
    r = row.one_or_none()
    return (r[0], float(r[1])) if r else None
