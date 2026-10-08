"""Opt-in route recording: travel legs derived from the phone's GPS.

Raw GPS points are never stored. Each leg keeps its times, way of travelling, grid cell and
a simplified line (at most ~30 points, rounded to ~100 m) to draw on the person's own map.
Legs are deleted after 7 days (worker tick) or whenever the person asks.

Revision ID: 0005
Revises: 0004
Create Date: 2026-10-05
"""

from collections.abc import Sequence

from alembic import op

revision: str = "0005"
down_revision: str | None = "0004"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

UP = [
    """
    CREATE TABLE travel_legs (
      id          bigserial PRIMARY KEY,
      user_id     uuid NOT NULL REFERENCES users(id) ON DELETE CASCADE,
      start_at    timestamptz NOT NULL,
      end_at      timestamptz NOT NULL CHECK (end_at > start_at),
      mode        text NOT NULL
                  CHECK (mode IN ('walk','run','cycle','bus_metro','two_wheeler','car')),
      cell_id     text NOT NULL,
      distance_m  real NOT NULL DEFAULT 0,
      path        jsonb NOT NULL DEFAULT '[]'::jsonb,
      source      text NOT NULL DEFAULT 'gps' CHECK (source IN ('gps','gps+activity')),
      created_at  timestamptz NOT NULL DEFAULT now()
    )
    """,
    "CREATE INDEX travel_legs_user_time ON travel_legs (user_id, start_at)",
    "CREATE INDEX travel_legs_cell ON travel_legs (cell_id)",
]

DOWN = ["DROP TABLE IF EXISTS travel_legs"]


def upgrade() -> None:
    for statement in UP:
        op.execute(statement)


def downgrade() -> None:
    for statement in DOWN:
        op.execute(statement)
