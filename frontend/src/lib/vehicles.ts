import { useQuery } from "@tanstack/react-query";
import { fetchVehicleCatalog } from "../api/client";
import type { LocationFilters, VehicleCatalog, VehicleMake, VehicleVariant } from "../api/types";

export function useVehicleCatalog() {
  return useQuery({
    queryKey: ["vehicles"],
    queryFn: fetchVehicleCatalog,
    staleTime: Infinity,
  });
}

export function compactVehicleQuery(value: string): string {
  return value
    .replace(/[يىئ]/g, "ی")
    .replace(/ك/g, "ک")
    .replace(/[أإآ]/g, "ا")
    .replace(/ة/g, "ه")
    .replace(/ؤ/g, "و")
    .replace(/\u200c/g, "")
    .toLowerCase()
    .replace(/[.+]/g, "")
    .replace(/[^\p{L}\p{N}]+/gu, "");
}

export function variantMatches(search: string, query: string): boolean {
  const compact = compactVehicleQuery(query);
  if (!compact) return true;
  return search.includes(compact);
}

export function findVehicle(
  catalog: VehicleCatalog | undefined,
  id: string | null,
): { make: VehicleMake; variant: VehicleVariant } | null {
  if (!catalog || !id) return null;
  for (const make of catalog.makes) {
    for (const model of make.models) {
      const variant = model.variants.find((item) => item.id === id);
      if (variant) return { make, variant };
    }
  }
  return null;
}

export function connectorsForQuery(filters: LocationFilters, vehicle: VehicleVariant | null): string[] {
  if (!vehicle || vehicle.station_standards.length === 0) return filters.connectors;
  if (filters.connectors.length === 0) return vehicle.station_standards;
  const allowed = new Set(vehicle.station_standards);
  return filters.connectors.filter((id) => allowed.has(id));
}

export function stationCompatibility(
  standards: string[],
  vehicle: VehicleVariant | null,
): "yes" | "no" | "unknown" | null {
  if (!vehicle) return null;
  if (standards.length === 0) return "unknown";
  return standards.some((standard) => vehicle.station_standards.includes(standard)) ? "yes" : "no";
}
