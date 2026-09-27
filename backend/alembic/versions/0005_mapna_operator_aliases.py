"""canonicalize Sharinet and eMapna operator aliases

Revision ID: 0005_mapna_operator_aliases
Revises: 0004_duplicate_candidates
Create Date: 2026-09-27
"""

from collections.abc import Sequence

from alembic import op

revision: str = "0005_mapna_operator_aliases"
down_revision: str | None = "0004_duplicate_candidates"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # Sharinet is Mapna's application/feed. It must remain visible as the data
    # source, but it is not a distinct network operator.
    op.execute(
        """
        DO $$
        DECLARE
            canonical_id uuid;
        BEGIN
            SELECT id INTO canonical_id
            FROM party.operators
            WHERE slug = 'mapna'
               OR name ILIKE '%مپنا%'
               OR lower(name) LIKE '%emapna%'
               OR lower(name) LIKE '%empana%'
               OR lower(name) LIKE '%sharinet%'
               OR name ILIKE '%شارینت%'
            ORDER BY CASE WHEN slug = 'mapna' THEN 0 WHEN slug = 'sharinet' THEN 1 ELSE 2 END
            LIMIT 1;

            IF canonical_id IS NOT NULL THEN
                UPDATE charging.locations
                SET operator_id = canonical_id
                WHERE operator_id IN (
                    SELECT id FROM party.operators
                    WHERE id <> canonical_id
                      AND (
                        name ILIKE '%مپنا%'
                        OR lower(name) LIKE '%emapna%'
                        OR lower(name) LIKE '%empana%'
                        OR lower(name) LIKE '%sharinet%'
                        OR name ILIKE '%شارینت%'
                      )
                );

                DELETE FROM party.operators
                WHERE id <> canonical_id
                  AND (
                    name ILIKE '%مپنا%'
                    OR lower(name) LIKE '%emapna%'
                    OR lower(name) LIKE '%empana%'
                    OR lower(name) LIKE '%sharinet%'
                    OR name ILIKE '%شارینت%'
                  );

                UPDATE party.operators SET slug = 'mapna', name = 'مپنا' WHERE id = canonical_id;
            END IF;
        END $$;
        """
    )


def downgrade() -> None:
    # The former aliases cannot be reconstructed after canonicalization.
    pass
