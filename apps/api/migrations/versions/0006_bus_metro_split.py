"""Bus and metro become separate ways of travelling.

Their CO2 per passenger-km differs (commute footprint), so one "bus_metro" option can't say
honestly which one is better. Existing "bus_metro" rows become "bus": the person can switch to
metro in their profile. Downgrade folds both back into "bus_metro".

Revision ID: 0006
Revises: 0005
Create Date: 2026-10-08
"""

from collections.abc import Sequence

from alembic import op

revision: str = "0006"
down_revision: str | None = "0005"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

UP = [
    "ALTER TABLE schedules DROP CONSTRAINT schedules_commute_mode_check",
    "UPDATE schedules SET commute_mode = 'bus' WHERE commute_mode = 'bus_metro'",
    """ALTER TABLE schedules ADD CONSTRAINT schedules_commute_mode_check
       CHECK (commute_mode IN ('walk','cycle','bus','metro','two_wheeler','car'))""",
    "ALTER TABLE travel_legs DROP CONSTRAINT travel_legs_mode_check",
    "UPDATE travel_legs SET mode = 'bus' WHERE mode = 'bus_metro'",
    """ALTER TABLE travel_legs ADD CONSTRAINT travel_legs_mode_check
       CHECK (mode IN ('walk','run','cycle','bus','metro','two_wheeler','car'))""",
]

DOWN = [
    "ALTER TABLE schedules DROP CONSTRAINT schedules_commute_mode_check",
    "UPDATE schedules SET commute_mode = 'bus_metro' WHERE commute_mode IN ('bus','metro')",
    """ALTER TABLE schedules ADD CONSTRAINT schedules_commute_mode_check
       CHECK (commute_mode IN ('walk','cycle','bus_metro','two_wheeler','car'))""",
    "ALTER TABLE travel_legs DROP CONSTRAINT travel_legs_mode_check",
    "UPDATE travel_legs SET mode = 'bus_metro' WHERE mode IN ('bus','metro')",
    """ALTER TABLE travel_legs ADD CONSTRAINT travel_legs_mode_check
       CHECK (mode IN ('walk','run','cycle','bus_metro','two_wheeler','car'))""",
]


def upgrade() -> None:
    for statement in UP:
        op.execute(statement)


def downgrade() -> None:
    for statement in DOWN:
        op.execute(statement)
