"""hours schedule on locations

Revision ID: 0003_hours_schedule
Revises: 0002_source_notes
Create Date: 2026-09-26
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0003_hours_schedule"
down_revision: str | None = "0002_source_notes"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

JSONB = postgresql.JSONB()


def upgrade() -> None:
    op.add_column(
        "locations",
        sa.Column("hours_schedule", JSONB),
        schema="charging",
    )


def downgrade() -> None:
    op.drop_column("locations", "hours_schedule", schema="charging")
