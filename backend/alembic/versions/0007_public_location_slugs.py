"""drop data-source names from public location slugs

Revision ID: 0007_public_location_slugs
Revises: 0006_xvision_operator_alias
Create Date: 2026-09-28
"""

from collections.abc import Sequence

from alembic import op
from sqlalchemy import text

from app.domain.slugs import public_location_slug

revision: str = "0007_public_location_slugs"
down_revision: str | None = "0006_xvision_operator_alias"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    conn = op.get_bind()
    rows = conn.execute(text("SELECT id, slug FROM charging.locations ORDER BY slug")).all()
    taken: set[str] = set()
    updates: list[tuple[object, str]] = []
    ordered = sorted(rows, key=lambda row: (public_location_slug(row.slug) != row.slug, row.slug))
    for row in ordered:
        base = public_location_slug(row.slug)
        candidate = base
        suffix = 2
        while candidate in taken:
            extra = f"-{suffix}"
            candidate = f"{base[: 70 - len(extra)]}{extra}"
            suffix += 1
        taken.add(candidate)
        if candidate != row.slug:
            updates.append((row.id, candidate))

    for location_id, _slug in updates:
        conn.execute(
            text("UPDATE charging.locations SET slug = :slug WHERE id = :id"),
            {"slug": f"migrating-{location_id.hex}", "id": location_id},
        )
    for location_id, slug in updates:
        conn.execute(
            text("UPDATE charging.locations SET slug = :slug WHERE id = :id"),
            {"slug": slug, "id": location_id},
        )


def downgrade() -> None:
    pass
