export type BBox = {
  south: number;
  west: number;
  north: number;
  east: number;
};

export type MapLocation = {
  id: string;
  slug?: string;
  name: string;
  lat: number;
  lng: number;
  operator_name: string | null;
  city: string | null;
  max_power_kw: number | null;
  connector_standards: string[];
  connector_labels: string[];
  power_types: string[];
  availability: string;
  availability_label: string;
  is_stale: boolean;
  available_connectors: number | null;
  total_connectors: number | null;
  source_codes: string[];
  distance_m: number | null;
};

export type MapResponse = {
  items: MapLocation[];
  count: number;
  truncated: boolean;
  limit: number;
};

export type Connector = {
  id: string;
  index: number;
  standard: string;
  standard_label: string;
  power_type: string | null;
  format: string | null;
  max_power_kw: number | null;
  status: string | null;
  status_label: string | null;
  raw_name: string | null;
};

export type Evse = {
  id: string;
  external_id: string;
  source_code: string;
  status: string;
  status_label: string;
  status_kind: string;
  reported_status: string | null;
  reported_status_label: string | null;
  status_updated_at: string | null;
  status_expires_at: string | null;
  is_stale: boolean;
  max_power_kw: number | null;
  counts: {
    total: number | null;
    available: number | null;
    charging: number | null;
    unavailable: number | null;
  } | null;
  connectors: Connector[];
};

export type LocationDetail = {
  id: string;
  slug?: string;
  name: string;
  name_en: string | null;
  operator_name: string | null;
  address: string | null;
  city: string | null;
  province: string | null;
  lat: number;
  lng: number;
  phone: string | null;
  website: string | null;
  is_public: boolean | null;
  is_24_7: boolean | null;
  is_reservable: boolean | null;
  hours_summary: string | null;
  hours_label: string | null;
  open_now: boolean | null;
  open_now_label: string | null;
  hours_schedule: {
    is_24_7?: boolean;
    intervals?: { weekdays: number[]; start: string; end: string }[];
    label?: string | null;
    parseable?: boolean;
    raw?: string | null;
  } | null;
  facilities: string[];
  notes: {
    source_code: string;
    kind: string;
    text: string;
    observed_at: string | null;
  }[];
  images: string[];
  availability: string;
  availability_label: string;
  is_stale: boolean;
  max_power_kw: number | null;
  source_codes: string[];
  sources: {
    code: string;
    name: string;
    external_id: string;
    attribution: string | null;
    last_seen_at: string | null;
  }[];
  evses: Evse[];
  price: {
    amount_rial: number;
    amount_toman: number;
    currency: string;
    unit: string;
    label: string | null;
    observed_at: string;
    source_code: string;
    is_free: boolean;
    varies: boolean;
  } | null;
  field_provenance: Record<string, { source?: string; priority?: number; at?: string }>;
  data_quality_score: number | null;
  updated_at: string;
};

export type SyncRun = {
  id: string;
  source: string;
  status: string;
  mode: string;
  started_at: string;
  finished_at: string | null;
  stats: Record<string, unknown>;
  error: string | null;
};

export type SourceStatus = {
  code: string;
  name: string;
  source_type: string;
  attribution: string | null;
  configured: boolean;
  active: boolean;
  last_run: SyncRun | null;
};

export type LocationFilters = {
  connectors: string[];
  minPowerKw: number | null;
  source: string | null;
  availability: string | null;
  vehicleId: string | null;
};

export type VehicleConnector = {
  code: string;
  display_name: string;
  current_type: string;
  station_standard: string;
};

export type VehicleVariant = {
  id: string;
  model_slug: string;
  model_name: string;
  variant_name: string;
  display_name: string;
  model_year: number | null;
  powertrain_type: string;
  powertrain_label: string;
  battery_kwh_min: number | null;
  battery_kwh_max: number | null;
  range_km: number | null;
  range_standard: string | null;
  ac_charge_limit_kw: number | null;
  dc_charge_limit_kw: number | null;
  connectors: VehicleConnector[];
  station_standards: string[];
  importer_name: string | null;
  importer_name_fa: string | null;
  verification_status: string;
  warnings: string[];
  no_dc_declared: boolean;
  search: string;
  source_external_id: string;
};

export type VehicleModel = {
  slug: string;
  name: string;
  variants: VehicleVariant[];
};

export type VehicleMake = {
  slug: string;
  name_en: string;
  name_fa: string;
  icon: string | null;
  models: VehicleModel[];
};

export type VehicleCatalog = {
  makes: VehicleMake[];
};

export type PlaceSuggestion = { title: string; address: string; lat: number; lng: number };

export type TripPlan = {
  status: "ok" | "no_feasible_route";
  reason: string | null;
  direct_distance_m: number;
  total_distance_m?: number;
  total_duration_s?: number;
  total_charging_duration_s?: number | null;
  total_stop_duration_s?: number | null;
  total_trip_duration_s?: number | null;
  effective_range_km: number;
  arrival_soc?: number;
  polyline: string;
  route_includes_stops?: boolean;
  stops: { id: string; slug: string; name: string; lat: number; lng: number; arrival_soc: number; departure_soc: number; power_kw: number | null; charging_power_kw?: number | null; charging_power_assumed?: boolean; charge_added_kwh?: number | null; charging_duration_s?: number | null; stop_duration_s?: number | null; availability: string }[];
  legs: { distance_m: number; duration_s: number; departure_soc: number; arrival_soc: number }[];
};
