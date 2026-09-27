import { useQuery } from "@tanstack/react-query";
import { fetchVehicleCatalog } from "../api/client";
import type { LocationFilters, VehicleCatalog, VehicleMake, VehicleVariant } from "../api/types";
import { brandHasMark } from "../ui/BrandMark";

/** Preferred make order at the top of the vehicle picker. */
export const PRIORITY_MAKE_SLUGS = ["honda", "volkswagen", "byd", "bmw", "toyota"] as const;

const PRIORITY_MAKE_RANK = new Map<string, number>(PRIORITY_MAKE_SLUGS.map((slug, index) => [slug, index]));

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

export function makeHasIcon(make: Pick<VehicleMake, "icon">): boolean {
  return brandHasMark(make.icon);
}

/** Sort makes: priority brands → brands with icons → remaining A–Z. */
export function compareMakesForDisplay(a: VehicleMake, b: VehicleMake): number {
  const aPriority = PRIORITY_MAKE_RANK.get(a.slug);
  const bPriority = PRIORITY_MAKE_RANK.get(b.slug);
  if (aPriority != null || bPriority != null) {
    if (aPriority == null) return 1;
    if (bPriority == null) return -1;
    return aPriority - bPriority;
  }

  const aIcon = makeHasIcon(a) ? 0 : 1;
  const bIcon = makeHasIcon(b) ? 0 : 1;
  if (aIcon !== bIcon) return aIcon - bIcon;

  return a.name_en.localeCompare(b.name_en, "en", { sensitivity: "base" });
}

export function sortMakesForDisplay(makes: VehicleMake[]): VehicleMake[] {
  return [...makes].sort(compareMakesForDisplay);
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
