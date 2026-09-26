"""Map MVP tables.

`field_provenance` records which source currently won each canonical field.
It is the small version of `integration.field_assertions` and can be expanded
without changing the location identity model.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from decimal import Decimal
from typing import Any

from geoalchemy2 import Geography
from sqlalchemy import (
    Boolean,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import ARRAY, JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TimestampMixin, new_id, utcnow


class Operator(Base, TimestampMixin):
    __tablename__ = "operators"
    __table_args__ = {"schema": "party"}

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=new_id)
    slug: Mapped[str] = mapped_column(String(80), unique=True)
    name: Mapped[str] = mapped_column(Text)


class Address(Base):
    __tablename__ = "addresses"
    __table_args__ = {"schema": "charging"}

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=new_id)
    country_code: Mapped[str] = mapped_column(String(2), default="IR")
    province: Mapped[str | None] = mapped_column(Text)
    city: Mapped[str | None] = mapped_column(Text)
    formatted_address_fa: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class Location(Base, TimestampMixin):
    __tablename__ = "locations"
    __table_args__ = (
        Index("locations_coordinates_gix", "coordinates", postgresql_using="gist"),
        {"schema": "charging"},
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=new_id)
    operator_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("party.operators.id"))
    canonical_name_fa: Mapped[str] = mapped_column(Text)
    canonical_name_en: Mapped[str | None] = mapped_column(Text)
    name_normalized: Mapped[str] = mapped_column(Text, default="")
    slug: Mapped[str] = mapped_column(String(120), unique=True)
    publish_status: Mapped[str] = mapped_column(String(32), default="published")
    access_type: Mapped[str] = mapped_column(String(32), default="unknown")
    is_24_7: Mapped[bool | None] = mapped_column(Boolean)
    is_public: Mapped[bool | None] = mapped_column(Boolean)
    is_reservable: Mapped[bool | None] = mapped_column(Boolean)
    timezone: Mapped[str] = mapped_column(String(64), default="Asia/Tehran")
    latitude: Mapped[Decimal] = mapped_column(Numeric(10, 7))
    longitude: Mapped[Decimal] = mapped_column(Numeric(10, 7))
    coordinates: Mapped[Any] = mapped_column(Geography(geometry_type="POINT", srid=4326))
    address_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("charging.addresses.id"))
    phone: Mapped[str | None] = mapped_column(Text)
    website_url: Mapped[str | None] = mapped_column(Text)
    hours_summary: Mapped[str | None] = mapped_column(Text)
    facilities: Mapped[list[str]] = mapped_column(ARRAY(Text), default=list)
    source_notes: Mapped[list] = mapped_column(JSONB, default=list)
    image_urls: Mapped[list[str]] = mapped_column(ARRAY(Text), default=list)
    source_codes: Mapped[list[str]] = mapped_column(ARRAY(Text), default=list)
    field_provenance: Mapped[dict] = mapped_column(JSONB, default=dict)
    data_quality_score: Mapped[Decimal | None] = mapped_column(Numeric(5, 2))
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    operator: Mapped[Operator | None] = relationship()
    address: Mapped[Address | None] = relationship()
    pools: Mapped[list[ChargingPool]] = relationship(back_populates="location")
    prices: Mapped[list[PriceObservation]] = relationship(back_populates="location")


class ChargingPool(Base, TimestampMixin):
    __tablename__ = "charging_pools"
    __table_args__ = (
        UniqueConstraint("location_id", "origin_source_code"),
        {"schema": "charging"},
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=new_id)
    location_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("charging.locations.id"))
    origin_source_code: Mapped[str] = mapped_column(String(32))
    name: Mapped[str] = mapped_column(Text)
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    location: Mapped[Location] = relationship(back_populates="pools")
    evses: Mapped[list[Evse]] = relationship(back_populates="pool")


class Evse(Base, TimestampMixin):
    __tablename__ = "evses"
    __table_args__ = (
        UniqueConstraint("origin_source_code", "origin_external_id"),
        {"schema": "charging"},
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=new_id)
    pool_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("charging.charging_pools.id"))
    origin_source_code: Mapped[str] = mapped_column(String(32))
    origin_external_id: Mapped[str] = mapped_column(Text)
    physical_reference: Mapped[str | None] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(32), default="UNKNOWN")
    status_kind: Mapped[str] = mapped_column(String(32), default="unknown")
    reported_status: Mapped[str | None] = mapped_column(String(32))
    status_updated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    status_expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    max_power_w: Mapped[int | None] = mapped_column(Integer)
    withdrawn_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    reported_total: Mapped[int | None] = mapped_column(Integer)
    reported_available: Mapped[int | None] = mapped_column(Integer)
    reported_charging: Mapped[int | None] = mapped_column(Integer)
    reported_unavailable: Mapped[int | None] = mapped_column(Integer)

    pool: Mapped[ChargingPool] = relationship(back_populates="evses")
    connectors: Mapped[list[Connector]] = relationship(
        back_populates="evse", cascade="all, delete-orphan"
    )


class Connector(Base, TimestampMixin):
    __tablename__ = "connectors"
    __table_args__ = (
        UniqueConstraint("evse_id", "connector_index"),
        {"schema": "charging"},
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=new_id)
    evse_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("charging.evses.id"))
    connector_index: Mapped[int] = mapped_column(Integer)
    standard: Mapped[str] = mapped_column(String(32))
    format: Mapped[str | None] = mapped_column(String(32))
    power_type: Mapped[str | None] = mapped_column(String(32))
    max_power_w: Mapped[int | None] = mapped_column(Integer)
    status: Mapped[str | None] = mapped_column(String(32))
    raw_name: Mapped[str | None] = mapped_column(Text)

    evse: Mapped[Evse] = relationship(back_populates="connectors")


class PriceObservation(Base):
    __tablename__ = "price_observations"
    __table_args__ = {"schema": "charging"}

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=new_id)
    location_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("charging.locations.id"))
    evse_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("charging.evses.id"))
    source_code: Mapped[str] = mapped_column(String(32))
    amount_minor: Mapped[int] = mapped_column(Integer)
    currency: Mapped[str] = mapped_column(String(8), default="IRR")
    per_unit: Mapped[str] = mapped_column(String(16), default="kwh")
    display_amount: Mapped[int] = mapped_column(Integer)
    display_unit: Mapped[str] = mapped_column(String(16), default="toman")
    label: Mapped[str | None] = mapped_column(Text)
    observed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    location: Mapped[Location] = relationship(back_populates="prices")


class SourceSystem(Base, TimestampMixin):
    __tablename__ = "source_systems"
    __table_args__ = {"schema": "integration"}

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=new_id)
    code: Mapped[str] = mapped_column(String(32), unique=True)
    name: Mapped[str] = mapped_column(Text)
    source_type: Mapped[str] = mapped_column(String(32))
    base_url: Mapped[str] = mapped_column(Text)
    trust_level: Mapped[int] = mapped_column(Integer, default=50)
    active: Mapped[bool] = mapped_column(Boolean, default=True)
    attribution_text: Mapped[str | None] = mapped_column(Text)


class ExternalRecord(Base):
    __tablename__ = "external_records"
    __table_args__ = (
        UniqueConstraint("source_system_id", "entity_type", "external_id"),
        {"schema": "integration"},
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=new_id)
    source_system_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("integration.source_systems.id"))
    entity_type: Mapped[str] = mapped_column(String(32))
    external_id: Mapped[str] = mapped_column(Text)
    canonical_entity_type: Mapped[str | None] = mapped_column(String(32))
    canonical_entity_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    content_hash: Mapped[str | None] = mapped_column(String(64))
    raw_payload: Mapped[dict | None] = mapped_column(JSONB)
    normalized_payload: Mapped[dict | None] = mapped_column(JSONB)
    is_present_at_source: Mapped[bool] = mapped_column(Boolean, default=True)
    validation_status: Mapped[str] = mapped_column(String(32), default="valid")
    validation_errors: Mapped[dict | None] = mapped_column(JSONB)
    attribution_text: Mapped[str | None] = mapped_column(Text)
    first_seen_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    last_seen_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    last_fetched_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    source: Mapped[SourceSystem] = relationship()


class ExternalLink(Base):
    __tablename__ = "external_links"
    __table_args__ = (
        UniqueConstraint(
            "left_external_record_id",
            "right_external_record_id",
            "relation_type",
            name="uq_external_links_pair",
        ),
        {"schema": "integration"},
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=new_id)
    left_external_record_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("integration.external_records.id")
    )
    right_external_record_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("integration.external_records.id")
    )
    relation_type: Mapped[str] = mapped_column(String(32))
    confidence: Mapped[Decimal] = mapped_column(Numeric(5, 4), default=Decimal("1"))
    evidence: Mapped[dict | None] = mapped_column(JSONB)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class SyncRun(Base):
    __tablename__ = "sync_runs"
    __table_args__ = {"schema": "integration"}

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=new_id)
    source_system_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("integration.source_systems.id"))
    status: Mapped[str] = mapped_column(String(32), default="pending")
    mode: Mapped[str] = mapped_column(String(32), default="full")
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    stats: Mapped[dict] = mapped_column(JSONB, default=dict)
    error: Mapped[str | None] = mapped_column(Text)

    source: Mapped[SourceSystem] = relationship()
