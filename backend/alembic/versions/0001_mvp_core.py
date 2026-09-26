"""mvp core: sources, locations, and map projection

Revision ID: 0001_mvp_core
Revises:
Create Date: 2026-09-26
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from geoalchemy2 import Geography
from sqlalchemy.dialects import postgresql

revision: str = "0001_mvp_core"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

UUID = postgresql.UUID(as_uuid=True)
JSONB = postgresql.JSONB()
TEXT_ARRAY = postgresql.ARRAY(sa.Text())


def upgrade() -> None:
    op.execute("CREATE EXTENSION IF NOT EXISTS postgis")
    op.execute("CREATE EXTENSION IF NOT EXISTS pgcrypto")
    op.execute("CREATE EXTENSION IF NOT EXISTS pg_trgm")
    op.execute("CREATE SCHEMA IF NOT EXISTS party")
    op.execute("CREATE SCHEMA IF NOT EXISTS charging")
    op.execute("CREATE SCHEMA IF NOT EXISTS integration")

    op.create_table(
        "operators",
        sa.Column("id", UUID, primary_key=True),
        sa.Column("slug", sa.String(80), nullable=False, unique=True),
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        schema="party",
    )
    op.create_table(
        "addresses",
        sa.Column("id", UUID, primary_key=True),
        sa.Column("country_code", sa.String(2), nullable=False, server_default="IR"),
        sa.Column("province", sa.Text()),
        sa.Column("city", sa.Text()),
        sa.Column("formatted_address_fa", sa.Text()),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        schema="charging",
    )
    op.create_table(
        "locations",
        sa.Column("id", UUID, primary_key=True),
        sa.Column("operator_id", UUID, sa.ForeignKey("party.operators.id")),
        sa.Column("canonical_name_fa", sa.Text(), nullable=False),
        sa.Column("canonical_name_en", sa.Text()),
        sa.Column("name_normalized", sa.Text(), nullable=False, server_default=""),
        sa.Column("slug", sa.String(120), nullable=False, unique=True),
        sa.Column("publish_status", sa.String(32), nullable=False, server_default="published"),
        sa.Column("access_type", sa.String(32), nullable=False, server_default="unknown"),
        sa.Column("is_24_7", sa.Boolean()),
        sa.Column("is_public", sa.Boolean()),
        sa.Column("is_reservable", sa.Boolean()),
        sa.Column("timezone", sa.String(64), nullable=False, server_default="Asia/Tehran"),
        sa.Column("latitude", sa.Numeric(10, 7), nullable=False),
        sa.Column("longitude", sa.Numeric(10, 7), nullable=False),
        sa.Column("coordinates", Geography(geometry_type="POINT", srid=4326), nullable=False),
        sa.Column("address_id", UUID, sa.ForeignKey("charging.addresses.id")),
        sa.Column("phone", sa.Text()),
        sa.Column("website_url", sa.Text()),
        sa.Column("hours_summary", sa.Text()),
        sa.Column("facilities", TEXT_ARRAY, nullable=False, server_default=sa.text("'{}'::text[]")),
        sa.Column("image_urls", TEXT_ARRAY, nullable=False, server_default=sa.text("'{}'::text[]")),
        sa.Column("source_codes", TEXT_ARRAY, nullable=False, server_default=sa.text("'{}'::text[]")),
        sa.Column("field_provenance", JSONB, nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("data_quality_score", sa.Numeric(5, 2)),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("deleted_at", sa.DateTime(timezone=True)),
        schema="charging",
    )
    op.create_index("locations_coordinates_gix", "locations", ["coordinates"], schema="charging", postgresql_using="gist")
    op.create_index("locations_lat_lng_idx", "locations", ["latitude", "longitude"], schema="charging")
    op.execute(
        "CREATE INDEX locations_name_trgm_idx ON charging.locations USING gin (canonical_name_fa gin_trgm_ops)"
    )
    op.create_table(
        "charging_pools",
        sa.Column("id", UUID, primary_key=True),
        sa.Column("location_id", UUID, sa.ForeignKey("charging.locations.id"), nullable=False),
        sa.Column("origin_source_code", sa.String(32), nullable=False),
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("deleted_at", sa.DateTime(timezone=True)),
        sa.UniqueConstraint("location_id", "origin_source_code", name="uq_charging_pools_location_source"),
        schema="charging",
    )
    op.create_table(
        "evses",
        sa.Column("id", UUID, primary_key=True),
        sa.Column("pool_id", UUID, sa.ForeignKey("charging.charging_pools.id"), nullable=False),
        sa.Column("origin_source_code", sa.String(32), nullable=False),
        sa.Column("origin_external_id", sa.Text(), nullable=False),
        sa.Column("physical_reference", sa.Text()),
        sa.Column("status", sa.String(32), nullable=False, server_default="UNKNOWN"),
        sa.Column("status_kind", sa.String(32), nullable=False, server_default="unknown"),
        sa.Column("reported_status", sa.String(32)),
        sa.Column("status_updated_at", sa.DateTime(timezone=True)),
        sa.Column("status_expires_at", sa.DateTime(timezone=True)),
        sa.Column("max_power_w", sa.Integer()),
        sa.Column("withdrawn_at", sa.DateTime(timezone=True)),
        sa.Column("reported_total", sa.Integer()),
        sa.Column("reported_available", sa.Integer()),
        sa.Column("reported_charging", sa.Integer()),
        sa.Column("reported_unavailable", sa.Integer()),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint("origin_source_code", "origin_external_id", name="uq_evses_origin"),
        schema="charging",
    )
    op.create_table(
        "connectors",
        sa.Column("id", UUID, primary_key=True),
        sa.Column("evse_id", UUID, sa.ForeignKey("charging.evses.id"), nullable=False),
        sa.Column("connector_index", sa.Integer(), nullable=False),
        sa.Column("standard", sa.String(32), nullable=False),
        sa.Column("format", sa.String(32)),
        sa.Column("power_type", sa.String(32)),
        sa.Column("max_power_w", sa.Integer()),
        sa.Column("status", sa.String(32)),
        sa.Column("raw_name", sa.Text()),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint("evse_id", "connector_index", name="uq_connectors_evse_index"),
        schema="charging",
    )
    op.create_table(
        "price_observations",
        sa.Column("id", UUID, primary_key=True),
        sa.Column("location_id", UUID, sa.ForeignKey("charging.locations.id"), nullable=False),
        sa.Column("evse_id", UUID, sa.ForeignKey("charging.evses.id")),
        sa.Column("source_code", sa.String(32), nullable=False),
        sa.Column("amount_minor", sa.Integer(), nullable=False),
        sa.Column("currency", sa.String(8), nullable=False, server_default="IRR"),
        sa.Column("per_unit", sa.String(16), nullable=False, server_default="kwh"),
        sa.Column("display_amount", sa.Integer(), nullable=False),
        sa.Column("display_unit", sa.String(16), nullable=False, server_default="toman"),
        sa.Column("label", sa.Text()),
        sa.Column("observed_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        schema="charging",
    )
    op.create_index("price_observations_evse_idx", "price_observations", ["evse_id", "observed_at"], schema="charging")
    op.create_table(
        "source_systems",
        sa.Column("id", UUID, primary_key=True),
        sa.Column("code", sa.String(32), nullable=False, unique=True),
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column("source_type", sa.String(32), nullable=False),
        sa.Column("base_url", sa.Text(), nullable=False),
        sa.Column("trust_level", sa.Integer(), nullable=False, server_default="50"),
        sa.Column("active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("attribution_text", sa.Text()),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        schema="integration",
    )
    op.create_table(
        "external_records",
        sa.Column("id", UUID, primary_key=True),
        sa.Column("source_system_id", UUID, sa.ForeignKey("integration.source_systems.id"), nullable=False),
        sa.Column("entity_type", sa.String(32), nullable=False),
        sa.Column("external_id", sa.Text(), nullable=False),
        sa.Column("canonical_entity_type", sa.String(32)),
        sa.Column("canonical_entity_id", UUID),
        sa.Column("content_hash", sa.String(64)),
        sa.Column("raw_payload", JSONB),
        sa.Column("normalized_payload", JSONB),
        sa.Column("is_present_at_source", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("validation_status", sa.String(32), nullable=False, server_default="valid"),
        sa.Column("validation_errors", JSONB),
        sa.Column("attribution_text", sa.Text()),
        sa.Column("first_seen_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("last_seen_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("last_fetched_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint(
            "source_system_id", "entity_type", "external_id", name="uq_external_records_identity"
        ),
        schema="integration",
    )
    op.create_table(
        "external_links",
        sa.Column("id", UUID, primary_key=True),
        sa.Column("left_external_record_id", UUID, sa.ForeignKey("integration.external_records.id"), nullable=False),
        sa.Column("right_external_record_id", UUID, sa.ForeignKey("integration.external_records.id"), nullable=False),
        sa.Column("relation_type", sa.String(32), nullable=False),
        sa.Column("confidence", sa.Numeric(5, 4), nullable=False, server_default="1"),
        sa.Column("evidence", JSONB),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint(
            "left_external_record_id",
            "right_external_record_id",
            "relation_type",
            name="uq_external_links_pair",
        ),
        schema="integration",
    )
    op.create_table(
        "sync_runs",
        sa.Column("id", UUID, primary_key=True),
        sa.Column("source_system_id", UUID, sa.ForeignKey("integration.source_systems.id"), nullable=False),
        sa.Column("status", sa.String(32), nullable=False, server_default="pending"),
        sa.Column("mode", sa.String(32), nullable=False, server_default="full"),
        sa.Column("started_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("finished_at", sa.DateTime(timezone=True)),
        sa.Column("stats", JSONB, nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("error", sa.Text()),
        schema="integration",
    )


def downgrade() -> None:
    op.drop_table("sync_runs", schema="integration")
    op.drop_table("external_links", schema="integration")
    op.drop_table("external_records", schema="integration")
    op.drop_table("source_systems", schema="integration")
    op.drop_index("price_observations_evse_idx", table_name="price_observations", schema="charging")
    op.drop_table("price_observations", schema="charging")
    op.drop_table("connectors", schema="charging")
    op.drop_table("evses", schema="charging")
    op.drop_table("charging_pools", schema="charging")
    op.execute("DROP INDEX IF EXISTS charging.locations_name_trgm_idx")
    op.drop_index("locations_lat_lng_idx", table_name="locations", schema="charging")
    op.drop_index("locations_coordinates_gix", table_name="locations", schema="charging")
    op.drop_table("locations", schema="charging")
    op.drop_table("addresses", schema="charging")
    op.drop_table("operators", schema="party")
    op.execute("DROP SCHEMA IF EXISTS integration CASCADE")
    op.execute("DROP SCHEMA IF EXISTS charging CASCADE")
    op.execute("DROP SCHEMA IF EXISTS party CASCADE")
