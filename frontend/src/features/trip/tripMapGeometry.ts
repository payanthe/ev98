import { latLng } from "leaflet";
import type { TripMapLeg, TripRouteKind } from "../../api/types";

export type RouteMode = "energy" | "slope";
export type RoutePoint = [number, number];
export type RouteGroup = { kind: TripRouteKind; paths: RoutePoint[][]; distance_m: number };

export function decodePolyline(encoded: string): [number, number][] {
  const points: [number, number][] = [];
  let lat = 0, lng = 0, index = 0;
  while (index < encoded.length) {
    const values: number[] = [];
    for (let coordinate = 0; coordinate < 2; coordinate++) {
      let shift = 0, result = 0, code: number;
      do {
        code = encoded.charCodeAt(index++) - 63;
        result |= (code & 31) << shift;
        shift += 5;
      } while (code >= 32 && index < encoded.length);
      values.push((result >> 1) ^ -(result & 1));
    }
    lat += values[0]; lng += values[1];
    points.push([lat / 1e5, lng / 1e5]);
  }
  return points;
}


export function groupRouteParts(legs: TripMapLeg[] | undefined, mode: RouteMode): RouteGroup[] {
  const groups = new Map<TripRouteKind, RouteGroup>();
  for (const leg of legs ?? []) {
    const points = decodePolyline(leg.polyline);
    if (points.length < 2 || leg.distance_m <= 0) continue;
    const cumulative = [0];
    for (let i = 1; i < points.length; i++) {
      cumulative.push(cumulative[i - 1] + latLng(points[i - 1]).distanceTo(points[i]));
    }
    const geometryLength = cumulative[cumulative.length - 1];
    if (geometryLength <= 0) continue;
    let previousMeters = 0;
    let nextVertex = 1;
    let from = points[0];
    for (const [endMeters, kind] of leg[mode]) {
      const end = Math.min(endMeters, leg.distance_m);
      if (end <= previousMeters) continue;
      const target = end / leg.distance_m * geometryLength;
      const positions = [from];
      while (nextVertex < points.length - 1 && cumulative[nextVertex] < target) {
        positions.push(points[nextVertex++]);
      }
      const before = nextVertex - 1;
      const step = cumulative[nextVertex] - cumulative[before];
      const fraction = step > 0 ? (target - cumulative[before]) / step : 1;
      const a = points[before], b = points[nextVertex];
      from = [a[0] + (b[0] - a[0]) * fraction, a[1] + (b[1] - a[1]) * fraction];
      positions.push(from);
      let group = groups.get(kind);
      if (!group) {
        group = { kind, paths: [], distance_m: 0 };
        groups.set(kind, group);
      }
      group.paths.push(positions);
      group.distance_m += end - previousMeters;
      previousMeters = end;
    }
  }
  return [...groups.values()];
}
