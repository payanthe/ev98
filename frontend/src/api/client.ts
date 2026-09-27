import type {
  BBox,
  LocationDetail,
  LocationFilters,
  MapResponse,
  SourceStatus,
  SyncRun,
  VehicleCatalog,
} from "./types";

export class ApiError extends Error {
  status: number;

  constructor(status: number, message: string) {
    super(message);
    this.status = status;
  }
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(path, {
    ...init,
    headers: {
      Accept: "application/json",
      ...(init?.body ? { "Content-Type": "application/json" } : {}),
      ...init?.headers,
    },
  });
  if (!response.ok) {
    let detail = response.statusText;
    try {
      const body = (await response.json()) as { detail?: string };
      if (body.detail) detail = body.detail;
    } catch {
      /* response had no JSON body */
    }
    throw new ApiError(response.status, detail);
  }
  return response.json() as Promise<T>;
}

export function fetchLocations(bbox: BBox | null, filters: LocationFilters, q?: string): Promise<MapResponse> {
  const params = new URLSearchParams();
  if (bbox) params.set("bbox", `${bbox.south},${bbox.west},${bbox.north},${bbox.east}`);
  if (q) params.set("q", q);
  for (const connector of filters.connectors) params.append("connector", connector);
  if (filters.minPowerKw) params.set("min_power_kw", String(filters.minPowerKw));
  if (filters.source) params.append("source", filters.source);
  if (filters.availability) params.set("availability", filters.availability);
  params.set("limit", q && !bbox ? "8" : "800");
  return request<MapResponse>(`/v1/locations/?${params.toString()}`);
}

export function fetchNearbyLocations(
  lat: number,
  lng: number,
  filters: LocationFilters,
  radiusM = 100_000,
  limit = 12,
): Promise<MapResponse> {
  const params = new URLSearchParams({
    lat: String(lat),
    lng: String(lng),
    radius_m: String(radiusM),
    limit: String(limit),
  });
  for (const connector of filters.connectors) params.append("connector", connector);
  if (filters.minPowerKw) params.set("min_power_kw", String(filters.minPowerKw));
  if (filters.source) params.append("source", filters.source);
  if (filters.availability) params.set("availability", filters.availability);
  return request<MapResponse>(`/v1/locations/?${params.toString()}`);
}

export function fetchVehicleCatalog(): Promise<VehicleCatalog> {
  return request<VehicleCatalog>("/v1/vehicles/");
}

export function fetchLocation(id: string): Promise<LocationDetail> {
  return request<LocationDetail>(`/v1/locations/${id}`);
}

export function fetchSources(): Promise<SourceStatus[]> {
  return request<SourceStatus[]>("/v1/ingestion/sources");
}

export function startSync(source: string, includeDetails = true): Promise<SyncRun> {
  return request<SyncRun>("/v1/ingestion/sync", {
    method: "POST",
    body: JSON.stringify({ source, include_details: includeDetails }),
  });
}

export function fetchRun(id: string): Promise<SyncRun> {
  return request<SyncRun>(`/v1/ingestion/runs/${id}`);
}
