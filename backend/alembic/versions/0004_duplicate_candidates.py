"""duplicate review queue

Revision ID: 0004_duplicate_candidates
Revises: 0003_hours_schedule
Create Date: 2026-09-27
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0004_duplicate_candidates"
down_revision: str | None = "0003_hours_schedule"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "duplicate_candidates",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("left_location_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("charging.locations.id"), nullable=False),
        sa.Column("right_location_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("charging.locations.id"), nullable=False),
        sa.Column("status", sa.String(32), nullable=False, server_default="pending"),
        sa.Column("confidence", sa.Numeric(5, 4), nullable=False),
        sa.Column("evidence", postgresql.JSONB(), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("resolved_at", sa.DateTime(timezone=True)),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("left_location_id", "right_location_id", name="uq_duplicate_candidate_pair"),
        schema="integration",
    )


def downgrade() -> None:
    op.drop_table("duplicate_candidates", schema="integration")
