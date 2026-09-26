"""location source notes

Revision ID: 0002_source_notes
Revises: 0001_mvp_core
Create Date: 2026-09-26
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0002_source_notes"
down_revision: str | None = "0001_mvp_core"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

JSONB = postgresql.JSONB()


def upgrade() -> None:
    op.add_column(
        "locations",
        sa.Column("source_notes", JSONB, nullable=False, server_default=sa.text("'[]'::jsonb")),
        schema="charging",
    )


def downgrade() -> None:
    op.drop_column("locations", "source_notes", schema="charging")
