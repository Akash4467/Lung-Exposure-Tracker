"""Trips out of town: on these days the person's air comes from the destination.

Revision ID: 0004
Revises: 0003
Create Date: 2026-10-05
"""

from collections.abc import Sequence

from alembic import op

revision: str = "0004"
down_revision: str | None = "0003"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

UP = [
    """
    CREATE TABLE trips (
      id          bigserial PRIMARY KEY,
      user_id     uuid NOT NULL REFERENCES users(id) ON DELETE CASCADE,
      label       text NOT NULL,
      lat         double precision NOT NULL CHECK (lat BETWEEN -90 AND 90),
      lon         double precision NOT NULL CHECK (lon BETWEEN -180 AND 180),
      cell_id     text NOT NULL,
      start_date  date NOT NULL,
      end_date    date NOT NULL CHECK (end_date >= start_date),
      created_at  timestamptz NOT NULL DEFAULT now()
    )
    """,
    "CREATE INDEX trips_user_dates ON trips (user_id, end_date)",
    "CREATE INDEX trips_cell ON trips (cell_id)",
]

DOWN = ["DROP TABLE IF EXISTS trips"]


def upgrade() -> None:
    for statement in UP:
        op.execute(statement)


def downgrade() -> None:
    for statement in DOWN:
        op.execute(statement)
