import type { PlaceSuggestion, TripPlan } from "../../api/types";

const CACHE_KEY = "ev98.trip.latestPlan.v3";
const MAX_AGE_MS = 15 * 60 * 1000;

function tripKey(origin: PlaceSuggestion, destination: PlaceSuggestion, vehicleId: string, soc: number) {
  return `${origin.lat.toFixed(6)},${origin.lng.toFixed(6)}|${destination.lat.toFixed(6)},${destination.lng.toFixed(6)}|${vehicleId}|${soc}`;
}

export function readCachedTrip(origin: PlaceSuggestion, destination: PlaceSuggestion, vehicleId: string, soc: number): TripPlan | null {
  try {
    const raw = sessionStorage.getItem(CACHE_KEY);
    if (!raw) return null;
    const saved = JSON.parse(raw) as { key?: string; savedAt?: number; plan?: TripPlan };
    if (saved.key !== tripKey(origin, destination, vehicleId, soc) || !saved.savedAt || Date.now() - saved.savedAt > MAX_AGE_MS) return null;
    if (saved.plan?.status !== "ok" || !Array.isArray(saved.plan.stops) || !Array.isArray(saved.plan.legs) || saved.plan.total_trip_duration_s == null) return null;
    return saved.plan;
  } catch {
    return null;
  }
}

export function cacheTrip(origin: PlaceSuggestion, destination: PlaceSuggestion, vehicleId: string, soc: number, plan: TripPlan) {
  if (plan.status !== "ok") return;
  try {
    sessionStorage.setItem(CACHE_KEY, JSON.stringify({ key: tripKey(origin, destination, vehicleId, soc), savedAt: Date.now(), plan }));
  } catch {
    /* Storage can be blocked without affecting trip planning. */
  }
}
