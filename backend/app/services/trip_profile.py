"""Aggregate the same energy samples used to plan a trip for its distance chart."""
import numpy as np

from app.services.trip_energy import LegEnergy, TerrainTrace
from app.services.trip_router import RoadLeg, encode_polyline


def _battery_trace(trace: TerrainTrace, departure: float, capacity: float) -> tuple[np.ndarray, np.ndarray]:
    prefixes = np.r_[0., np.cumsum(trace.draw_kwh - trace.regen_kwh)] / capacity * 100
    overflow = np.maximum(0, departure - 100 - np.minimum.accumulate(prefixes))
    soc = departure - prefixes - overflow
    stored = np.maximum(0, trace.regen_kwh - np.diff(overflow) * capacity / 100)
    return soc, stored


def _route_runs(meters: np.ndarray, labels: np.ndarray) -> list[tuple[float, str]]:
    changes = np.flatnonzero(labels[1:] != labels[:-1]) + 1
    ends = np.r_[changes, len(labels)]
    return [(float(meters[end]), str(labels[end - 1])) for end in ends]


def map_leg(leg: RoadLeg, profile: LegEnergy, departure: float, capacity: float) -> dict | None:
    if len(leg.shape) < 2 or leg.distance_m <= 0:
        return None
    trace = profile.terrain
    if trace is None:
        energy = slope = [(leg.distance_m, "unknown")]
    else:
        _, stored = _battery_trace(trace, departure, capacity)
        net = stored - trace.draw_kwh
        flow = np.where(net > 1e-6, "recovery", np.where(net < -1e-6, "consumption", "neutral"))
        grade = np.where(trace.uphill_m > 0, "uphill", np.where(trace.downhill_m > 0, "downhill", "level"))
        energy = _route_runs(trace.meters, flow)
        slope = _route_runs(trace.meters, grade)
    return {"polyline": encode_polyline(leg.shape), "distance_m": leg.distance_m,
            "energy": energy, "slope": slope}


def chart_leg(leg: RoadLeg, profile: LegEnergy, offset: int, departure: float,
              capacity: float, interval: float) -> list[dict]:
    trace = profile.terrain
    length = round(leg.distance_m)
    if trace is None:
        return [{
            "start_m": offset, "end_m": offset + length,
            "start_elevation_m": None, "end_elevation_m": None, "resolution_m": None,
            "start_soc": round(departure, 2), "end_soc": round(profile.arrival(departure), 2),
            "draw_kwh": round(profile.net_soc * capacity / 100, 4), "regen_kwh": 0.,
            "uphill_m": 0., "downhill_m": 0.,
        }]
    soc, stored = _battery_trace(trace, departure, capacity)
    borders = [v for span in trace.quality for v in (span.start_m, span.end_m)]
    boundaries = np.searchsorted(trace.meters, np.r_[np.arange(interval, leg.distance_m, interval), borders])
    boundaries = np.unique(np.r_[0, boundaries, len(trace.meters) - 1])
    scale = length / leg.distance_m
    segments = []
    for a, b in zip(boundaries[:-1], boundaries[1:]):
        segments.append({
            "start_m": offset + round(trace.meters[a] * scale), "end_m": offset + round(trace.meters[b] * scale),
            "start_elevation_m": round(trace.heights[a], 1), "end_elevation_m": round(trace.heights[b], 1),
            "resolution_m": trace.resolution_m,
            "start_soc": round(soc[a], 2), "end_soc": round(soc[b], 2),
            "draw_kwh": round(float(trace.draw_kwh[a:b].sum()), 4),
            "regen_kwh": round(float(stored[a:b].sum()), 4),
            "uphill_m": round(float(trace.uphill_m[a:b].sum() * scale), 2),
            "downhill_m": round(float(trace.downhill_m[a:b].sum() * scale), 2),
        })
    return segments


def chart_quality(leg: RoadLeg, profile: LegEnergy, offset: int) -> list[dict]:
    if profile.terrain is None or leg.distance_m <= 0:
        return []
    scale = round(leg.distance_m) / leg.distance_m
    spans = []
    for span in profile.terrain.quality:
        start = offset + round(span.start_m * scale)
        end = offset + round(span.end_m * scale)
        if end > start:
            spans.append({"start_m": start, "end_m": end, "kind": span.kind})
    return spans


def chart_summary(segments: list[dict], stops: list[dict], total_distance_m: int,
                  quality_spans: list[dict] | None = None, structures_unchecked_m: int = 0) -> dict:
    uphill = round(sum(s["uphill_m"] for s in segments))
    downhill = round(sum(s["downhill_m"] for s in segments))
    unprofiled = sum(s["end_m"] - s["start_m"] for s in segments if s["resolution_m"] is None)
    return {
        "segments": segments,
        "stops": stops,
        "quality_spans": quality_spans or [],
        "structures_unchecked_m": structures_unchecked_m,
        "uphill_m": uphill,
        "downhill_m": downhill,
        "mostly_flat_m": max(0, total_distance_m - unprofiled - uphill - downhill),
        "unprofiled_m": unprofiled,
        "draw_kwh": round(sum(s["draw_kwh"] for s in segments), 2),
        "regen_kwh": round(sum(s["regen_kwh"] for s in segments), 2),
    }
