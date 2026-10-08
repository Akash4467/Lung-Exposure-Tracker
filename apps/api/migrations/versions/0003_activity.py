"""Lung Load: measured activity (manual logs, phone activity recognition, Health Connect).

Revision ID: 0003
Revises: 0002
Create Date: 2026-10-05
"""

from collections.abc import Sequence

from alembic import op

revision: str = "0003"
down_revision: str | None = "0002"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

UP = [
    """
    CREATE TABLE activity_intervals (
      id             bigserial PRIMARY KEY,
      user_id        uuid NOT NULL REFERENCES users(id) ON DELETE CASCADE,
      start_at       timestamptz NOT NULL,
      end_at         timestamptz NOT NULL CHECK (end_at > start_at),
      kind           text NOT NULL CHECK (kind IN ('asleep','light','walk','run','cycle')),
      met            real CHECK (met BETWEEN 0.5 AND 25),
      outdoors       boolean,
      source         text NOT NULL DEFAULT 'manual'
                     CHECK (source IN ('manual','activity_recognition','health_connect')),
      heart_rate     real,
      steps_per_min  real,
      created_at     timestamptz NOT NULL DEFAULT now()
    )
    """,
    "CREATE INDEX activity_intervals_user_time ON activity_intervals (user_id, start_at)",
    # Visits can now say the person was running.
    "ALTER TABLE visits DROP CONSTRAINT visits_activity_check",
    "ALTER TABLE visits ADD CONSTRAINT visits_activity_check "
    "CHECK (activity IN ('asleep','light','walk','run','cycle'))",
]

DOWN = [
    "UPDATE visits SET activity = 'walk' WHERE activity = 'run'",
    "ALTER TABLE visits DROP CONSTRAINT visits_activity_check",
    "ALTER TABLE visits ADD CONSTRAINT visits_activity_check "
    "CHECK (activity IN ('asleep','light','walk','cycle'))",
    "DROP TABLE IF EXISTS activity_intervals",
]


def upgrade() -> None:
    for statement in UP:
        op.execute(statement)


def downgrade() -> None:
    for statement in DOWN:
        op.execute(statement)
