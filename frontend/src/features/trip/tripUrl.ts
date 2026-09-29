import type { PlaceSuggestion } from "../../api/types";

export type TripUrlState = {
  origin: PlaceSuggestion | null;
  destination: PlaceSuggestion | null;
  vehicleId: string | null;
  soc: number;
};

const VEHICLE_ID = /^[0-9a-f]{8}-[0-9a-f]{4}-[1-8][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/i;

function readPlace(params: URLSearchParams, key: "from" | "to"): PlaceSuggestion | null {
  const coordinates = params.get(key)?.split(",");
  if (coordinates?.length !== 2 || !coordinates[0].trim() || !coordinates[1].trim()) return null;
  const lat = Number(coordinates[0]);
  const lng = Number(coordinates[1]);
  if (!Number.isFinite(lat) || !Number.isFinite(lng) || Math.abs(lat) > 90 || Math.abs(lng) > 180) return null;
  const fallback = `${lat.toFixed(5)}, ${lng.toFixed(5)}`;
  const title = params.get(`${key}_name`)?.trim().slice(0, 160) || fallback;
  const address = params.get(`${key}_address`)?.trim().slice(0, 240) || title;
  return { lat, lng, title, address };
}

export function readTripUrl(search: string = window.location.search): TripUrlState {
  const params = new URLSearchParams(search);
  const charge = Number(params.get("soc"));
  const vehicleId = params.get("vehicle");
  return {
    origin: readPlace(params, "from"),
    destination: readPlace(params, "to"),
    vehicleId: vehicleId && VEHICLE_ID.test(vehicleId) ? vehicleId : null,
    soc: Number.isInteger(charge) && charge >= 1 && charge <= 100 ? charge : 60,
  };
}

function writePlace(params: URLSearchParams, key: "from" | "to", place: PlaceSuggestion | null) {
  params.delete(key);
  params.delete(`${key}_name`);
  params.delete(`${key}_address`);
  if (!place) return;
  params.set(key, `${place.lat.toFixed(6)},${place.lng.toFixed(6)}`);
  params.set(`${key}_name`, place.title);
  if (place.address && place.address !== place.title) params.set(`${key}_address`, place.address);
}

export function tripUrl(base: string, state: TripUrlState): URL {
  const url = new URL(base);
  writePlace(url.searchParams, "from", state.origin);
  writePlace(url.searchParams, "to", state.destination);
  if (state.vehicleId) url.searchParams.set("vehicle", state.vehicleId);
  else url.searchParams.delete("vehicle");
  if (state.soc !== 60) url.searchParams.set("soc", String(state.soc));
  else url.searchParams.delete("soc");
  return url;
}
