"""public station slugs start with the province detected from boundaries

Revision ID: 0008_province_location_slugs
Revises: 0007_public_location_slugs
Create Date: 2026-09-28
"""

from collections.abc import Sequence

from alembic import op
from sqlalchemy import text

from app.domain.provinces import province_at
from app.domain.slugs import station_slug

revision: str = "0008_province_location_slugs"
down_revision: str | None = "0007_public_location_slugs"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_MAX = 120


def upgrade() -> None:
    conn = op.get_bind()
    rows = conn.execute(
        text(
            """
            SELECT id, canonical_name_fa, latitude::float, longitude::float
            FROM charging.locations
            ORDER BY id
            """
        )
    ).all()
    taken: set[str] = set()
    planned: list[tuple[object, str, str]] = []
    for row in rows:
        province = province_at(float(row.latitude), float(row.longitude))
        base = station_slug(row.canonical_name_fa, province)[:_MAX].strip("-") or "ایستگاه"
        candidate = base
        suffix = 2
        while candidate in taken:
            extra = f"-{suffix}"
            candidate = f"{base[: _MAX - len(extra)].strip('-')}{extra}"
            suffix += 1
        taken.add(candidate)
        planned.append((row.id, candidate))

    for location_id, _slug in planned:
        conn.execute(
            text("UPDATE charging.locations SET slug = :slug WHERE id = :id"),
            {"slug": f"migrating-{location_id.hex}", "id": location_id},
        )
    for location_id, slug in planned:
        conn.execute(
            text("UPDATE charging.locations SET slug = :slug WHERE id = :id"),
            {"slug": slug, "id": location_id},
        )


def downgrade() -> None:
    pass
