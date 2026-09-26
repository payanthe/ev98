import uuid
from datetime import datetime

from pydantic import BaseModel, Field


class MapLocation(BaseModel):
    id: uuid.UUID
    name: str
    lat: float
    lng: float
    operator_name: str | None = None
    city: str | None = None
    max_power_kw: float | None = None
    connector_standards: list[str]
    connector_labels: list[str]
    power_types: list[str]
    availability: str
    availability_label: str
    is_stale: bool
    available_connectors: int | None = None
    total_connectors: int | None = None
    source_codes: list[str]
    distance_m: int | None = None


class MapResponse(BaseModel):
    items: list[MapLocation]
    count: int
    truncated: bool
    limit: int


class CountsOut(BaseModel):
    total: int | None = None
    available: int | None = None
    charging: int | None = None
    unavailable: int | None = None


class ConnectorOut(BaseModel):
    id: uuid.UUID
    index: int
    standard: str
    standard_label: str
    power_type: str | None = None
    format: str | None = None
    max_power_kw: float | None = None
    status: str | None = None
    status_label: str | None = None
    raw_name: str | None = None


class EvseOut(BaseModel):
    id: uuid.UUID
    external_id: str
    source_code: str
    status: str
    status_label: str
    status_kind: str
    reported_status: str | None = None
    reported_status_label: str | None = None
    status_updated_at: datetime | None = None
    status_expires_at: datetime | None = None
    is_stale: bool
    max_power_kw: float | None = None
    counts: CountsOut | None = None
    connectors: list[ConnectorOut]


class SourceOut(BaseModel):
    code: str
    name: str
    external_id: str
    attribution: str | None = None
    last_seen_at: datetime | None = None


class PriceOut(BaseModel):
    amount_rial: int
    amount_toman: int
    currency: str
    unit: str
    label: str | None = None
    observed_at: datetime
    source_code: str
    is_free: bool
    varies: bool


class SourceNoteOut(BaseModel):
    source_code: str
    kind: str
    text: str
    observed_at: datetime | None = None


class LocationDetail(BaseModel):
    id: uuid.UUID
    name: str
    name_en: str | None = None
    operator_name: str | None = None
    address: str | None = None
    city: str | None = None
    province: str | None = None
    lat: float
    lng: float
    phone: str | None = None
    website: str | None = None
    is_public: bool | None = None
    is_24_7: bool | None = None
    is_reservable: bool | None = None
    hours_summary: str | None = None
    hours_label: str | None = None
    open_now: bool | None = None
    open_now_label: str | None = None
    hours_schedule: dict | None = None
    facilities: list[str]
    notes: list[SourceNoteOut]
    images: list[str]
    availability: str
    availability_label: str
    is_stale: bool
    max_power_kw: float | None = None
    source_codes: list[str]
    sources: list[SourceOut]
    evses: list[EvseOut]
    price: PriceOut | None = None
    field_provenance: dict
    data_quality_score: float | None = None
    updated_at: datetime


class SyncRequest(BaseModel):
    source: str = Field(pattern="^(sharinet|ocm|abrp)$")
    include_details: bool = True


class SyncRunOut(BaseModel):
    id: uuid.UUID
    source: str
    status: str
    mode: str
    started_at: datetime
    finished_at: datetime | None = None
    stats: dict
    error: str | None = None


class SourceStatusOut(BaseModel):
    code: str
    name: str
    source_type: str
    attribution: str | None = None
    configured: bool
    active: bool
    last_run: SyncRunOut | None = None
