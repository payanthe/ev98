from dataclasses import asdict, dataclass, field
from datetime import datetime


@dataclass
class NormalizedConnector:
    index: int
    standard: str
    power_type: str | None = None
    format: str | None = None
    max_power_w: int | None = None
    status: str | None = None
    raw_name: str | None = None


@dataclass
class NormalizedNote:
    text: str
    kind: str = "access"
    observed_at: datetime | None = None


@dataclass
class NormalizedEvse:
    external_id: str
    status: str
    status_kind: str
    connectors: list[NormalizedConnector] = field(default_factory=list)
    max_power_w: int | None = None
    reported_status: str | None = None
    counts: dict | None = None
    physical_reference: str | None = None


@dataclass
class NormalizedRecord:
    source_code: str
    entity_type: str
    external_id: str
    name: str
    lat: float
    lng: float
    evses: list[NormalizedEvse] = field(default_factory=list)
    name_en: str | None = None
    address: str | None = None
    city: str | None = None
    province: str | None = None
    operator_name: str | None = None
    phone: str | None = None
    website: str | None = None
    is_public: bool | None = None
    is_24_7: bool | None = None
    hours_summary: str | None = None
    access_type: str = "unknown"
    facilities: list[str] = field(default_factory=list)
    notes: list[NormalizedNote] = field(default_factory=list)
    image_urls: list[str] = field(default_factory=list)
    attribution: str | None = None
    ocm_external_id: str | None = None
    has_dynamic_status: bool | None = None
    price_toman_per_kwh: int | None = None
    price_label: str | None = None
    price_observed_at: datetime | None = None
    is_free: bool = False
    is_reservable: bool | None = None
    publish: bool = True
    detail_fetched: bool = False
    raw: dict = field(default_factory=dict)


def _jsonable(value):
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, dict):
        return {key: _jsonable(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_jsonable(item) for item in value]
    return value


def normalized_dict(record: NormalizedRecord) -> dict:
    payload = asdict(record)
    payload.pop("raw", None)
    return _jsonable(payload)
