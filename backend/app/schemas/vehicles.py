from pydantic import BaseModel, Field


class VehicleConnectorOut(BaseModel):
    code: str
    display_name: str
    current_type: str
    station_standard: str


class VehicleVariantOut(BaseModel):
    id: str
    model_slug: str
    model_name: str
    variant_name: str
    display_name: str
    model_year: int | None = None
    powertrain_type: str
    powertrain_label: str
    battery_kwh_min: float | None = None
    battery_kwh_max: float | None = None
    range_km: float | None = None
    range_standard: str | None = None
    ac_charge_limit_kw: float | None = None
    dc_charge_limit_kw: float | None = None
    connectors: list[VehicleConnectorOut]
    station_standards: list[str]
    importer_name: str | None = None
    importer_name_fa: str | None = None
    verification_status: str
    warnings: list[str] = Field(default_factory=list)
    no_dc_declared: bool
    search: str
    source_external_id: str


class VehicleModelOut(BaseModel):
    slug: str
    name: str
    variants: list[VehicleVariantOut]


class VehicleMakeOut(BaseModel):
    slug: str
    name_en: str
    name_fa: str
    icon: str | None = None
    models: list[VehicleModelOut]


class VehicleCatalogOut(BaseModel):
    makes: list[VehicleMakeOut]
