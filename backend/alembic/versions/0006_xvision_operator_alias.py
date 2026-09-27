"""canonicalize XVision / XV Go operator aliases

Revision ID: 0006_xvision_operator_alias
Revises: 0005_mapna_operator_aliases
Create Date: 2026-09-27
"""

from collections.abc import Sequence

from alembic import op

revision: str = "0006_xvision_operator_alias"
down_revision: str | None = "0005_mapna_operator_aliases"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute(
        """
        DO $$
        DECLARE
            canonical_id uuid;
        BEGIN
            SELECT id INTO canonical_id
            FROM party.operators
            WHERE slug = 'xvision'
               OR name ILIKE '%ایکس ویژن%'
               OR name ILIKE '%ایکسویژن%'
               OR lower(name) LIKE '%xvision%'
               OR lower(name) LIKE '%xv go%'
               OR lower(name) LIKE '%xvgo%'
            ORDER BY CASE WHEN slug = 'xvision' THEN 0 ELSE 1 END
            LIMIT 1;

            IF canonical_id IS NOT NULL THEN
                UPDATE charging.locations
                SET operator_id = canonical_id
                WHERE operator_id IN (
                    SELECT id FROM party.operators
                    WHERE id <> canonical_id
                      AND (
                        name ILIKE '%ایکس ویژن%'
                        OR name ILIKE '%ایکسویژن%'
                        OR lower(name) LIKE '%xvision%'
                        OR lower(name) LIKE '%xv go%'
                        OR lower(name) LIKE '%xvgo%'
                      )
                );

                DELETE FROM party.operators
                WHERE id <> canonical_id
                  AND (
                    name ILIKE '%ایکس ویژن%'
                    OR name ILIKE '%ایکسویژن%'
                    OR lower(name) LIKE '%xvision%'
                    OR lower(name) LIKE '%xv go%'
                    OR lower(name) LIKE '%xvgo%'
                  );

                UPDATE party.operators
                SET slug = 'xvision', name = 'ایکس ویژن'
                WHERE id = canonical_id;
            END IF;
        END $$;
        """
    )


def downgrade() -> None:
    # Former aliases cannot be reconstructed after canonicalization.
    pass
