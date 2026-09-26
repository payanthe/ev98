import type { LocationFilters } from "../api/types";

export const CONNECTOR_FILTERS = [
  { id: "CCS_2", label: "CCS2" },
  { id: "GBT_DC", label: "GB/T DC" },
  { id: "TYPE_2", label: "Type 2" },
  { id: "CHADEMO", label: "CHAdeMO" },
  { id: "GBT_AC", label: "GB/T AC" },
  { id: "TYPE_1", label: "Type 1" },
] as const;

export const POWER_FILTERS = [
  { value: 22, label: "+۲۲" },
  { value: 50, label: "+۵۰" },
  { value: 120, label: "+۱۲۰" },
] as const;

export const EMPTY_FILTERS: LocationFilters = {
  connectors: [],
  minPowerKw: null,
  source: null,
  availability: null,
  vehicleId: null,
};

const VEHICLE_ID = /^[0-9a-f]{8}-[0-9a-f]{4}-[1-8][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/i;
const VEHICLE_STORAGE_KEY = "ev98.vehicle";

function validVehicleId(value: string | null): string | null {
  if (!value || !VEHICLE_ID.test(value)) return null;
  return value;
}

function readStoredVehicle(): string | null {
  try {
    return validVehicleId(localStorage.getItem(VEHICLE_STORAGE_KEY));
  } catch {
    return null;
  }
}

function writeStoredVehicle(vehicleId: string | null) {
  try {
    if (vehicleId) localStorage.setItem(VEHICLE_STORAGE_KEY, vehicleId);
    else localStorage.removeItem(VEHICLE_STORAGE_KEY);
  } catch {
    /* private mode or blocked storage */
  }
}

const CONNECTOR_IDS = new Set<string>(CONNECTOR_FILTERS.map((item) => item.id));
const POWER_VALUES = new Set<number>(POWER_FILTERS.map((item) => item.value));

export function activeFilterCount(filters: LocationFilters): number {
  return (
    filters.connectors.length +
    (filters.vehicleId ? 1 : 0) +
    (filters.minPowerKw ? 1 : 0) +
    (filters.availability ? 1 : 0) +
    (filters.source ? 1 : 0)
  );
}

export function filterSummary(filters: LocationFilters, vehicleLabel?: string | null): string {
  const parts: string[] = [];
  if (vehicleLabel) parts.push(vehicleLabel);
  if (!vehicleLabel || filters.connectors.length > 0) {
    for (const id of filters.connectors) {
      const match = CONNECTOR_FILTERS.find((item) => item.id === id);
      if (match) parts.push(match.label);
    }
  }
  const power = POWER_FILTERS.find((item) => item.value === filters.minPowerKw);
  if (power) parts.push(power.label);
  if (filters.availability === "available") parts.push("فقط آزاد");
  if (filters.source === "sharinet") parts.push("شارینت");
  return parts.join("، ");
}

export function readMapState(): { selectedId: string | null; filters: LocationFilters } {
  const params = new URLSearchParams(window.location.search);
  const power = Number(params.get("min_power"));
  return {
    selectedId: params.get("location"),
    filters: {
      connectors: params.getAll("connector").filter((id) => CONNECTOR_IDS.has(id)),
      minPowerKw: POWER_VALUES.has(power) ? power : null,
      source: params.get("source") === "sharinet" ? "sharinet" : null,
      availability: params.get("availability") === "available" ? "available" : null,
      vehicleId: validVehicleId(params.get("vehicle")) ?? readStoredVehicle(),
    },
  };
}

export function writeMapState(selectedId: string | null, filters: LocationFilters) {
  const params = new URLSearchParams();
  if (selectedId) params.set("location", selectedId);
  for (const connector of filters.connectors) params.append("connector", connector);
  if (filters.minPowerKw) params.set("min_power", String(filters.minPowerKw));
  if (filters.source) params.set("source", filters.source);
  if (filters.availability) params.set("availability", filters.availability);
  if (filters.vehicleId) params.set("vehicle", filters.vehicleId);
  writeStoredVehicle(filters.vehicleId);
  const next = params.toString();
  const url = next ? `?${next}` : window.location.pathname;
  if (`${window.location.pathname}${window.location.search}` !== (next ? `${window.location.pathname}?${next}` : window.location.pathname)) {
    window.history.replaceState(null, "", url);
  }
}
