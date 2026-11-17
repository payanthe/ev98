"""Assess lateral terrain sensitivity and estimate profiles across road structures."""
from dataclasses import dataclass
from typing import Literal

import numpy as np

from app.api.errors import AppError
from app.services.elevation import ElevationUnavailable, distance_m, read_elevations, smooth_height
from app.services.trip_router import RoadLeg, _engine_request, decode_polyline

SpanKind = Literal["uncertain", "bridge", "tunnel"]
SIDE_OFFSET_M = 15
LATERAL_SPREAD_M = 12
SPIKE_DEVIATION_M = 6


@dataclass(frozen=True)
class TerrainSpan:
    start_m: float
    end_m: float
    kind: SpanKind


def structure_spans(leg: RoadLeg, length: float) -> list[TerrainSpan] | None:
    """Use exact graph edges from the same route shape, without rematching a nearby road."""
    try:
        result = _engine_request("trace_attributes", {
            "shape": [{"lat": p.lat, "lon": p.lng} for p in leg.shape],
            "shape_match": "edge_walk",
            "filters": {"action": "include", "attributes": [
                "shape", "edge.begin_shape_index", "edge.end_shape_index", "edge.bridge", "edge.tunnel",
            ]},
        })
        shape = decode_polyline(result["shape"], precision=6)
        if len(shape) < 2 or not result["edges"]:
            return None
        coords = [(p.lng, p.lat) for p in shape]
        if max(distance_m(coords[0], (leg.shape[0].lng, leg.shape[0].lat)),
               distance_m(coords[-1], (leg.shape[-1].lng, leg.shape[-1].lat))) > 12:
            return None
        meters = np.r_[0., np.cumsum([distance_m(a, b) for a, b in zip(coords, coords[1:])])]
        if meters[-1] <= 0 or abs(meters[-1] - length) > max(15, length * .01):
            return None
        meters *= length / meters[-1]
        spans: list[TerrainSpan] = []
        for edge in result["edges"]:
            kind = "tunnel" if edge["tunnel"] else "bridge" if edge["bridge"] else None
            if not kind:
                continue
            a, b = edge["begin_shape_index"], edge["end_shape_index"]
            if not 0 <= a <= b < len(meters):
                return None
            start, end = float(meters[a]), float(meters[b])
            if end <= start:
                continue
            if spans and spans[-1].kind == kind and start <= spans[-1].end_m + 1e-3:
                spans[-1] = TerrainSpan(spans[-1].start_m, end, kind)
            else:
                spans.append(TerrainSpan(start, end, kind))
        return spans
    except (AppError, KeyError, TypeError, ValueError, IndexError):
        return None


def uncertain_samples(tiles, coords, central):
    """Side samples detect ambiguity. Only centerline elevations feed the model."""
    lon_scale = 111_320 * np.cos(np.radians(coords[:, 1]))
    vx, vy = (np.gradient(coords, axis=0) * np.column_stack((
        lon_scale, np.full(len(coords), 111_132.),
    ))).T
    norm = np.hypot(vx, vy)
    normal = np.zeros_like(coords)
    np.divide(-vy, norm * lon_scale, out=normal[:, 0], where=norm > 1e-6)
    np.divide(vx, norm * 111_132., out=normal[:, 1], where=norm > 1e-6)
    left, right = np.split(read_elevations(tiles, np.concatenate((
        coords + SIDE_OFFSET_M * normal, coords - SIDE_OFFSET_M * normal,
    )), require_complete=False), 2)
    spread = np.fmax(np.fmax(central, left), right) - np.fmin(np.fmin(central, left), right)
    return spread >= LATERAL_SPREAD_M


def _lateral_spans(meters, uncertain):
    flagged = uncertain[:-1] | uncertain[1:]
    edges = np.flatnonzero(np.diff(np.r_[False, flagged, False]))
    return [TerrainSpan(float(meters[a]), float(meters[b]), "uncertain")
            for a, b in zip(edges[::2], edges[1::2], strict=True)]


def _repair_spikes(meters, raw, uncertain, on_ground, window_m):
    cleaned = raw.copy()
    for i in np.flatnonzero(uncertain & on_ground):
        a, b = np.searchsorted(meters, [meters[i] - window_m / 2, meters[i] + window_m / 2])
        left = np.flatnonzero(on_ground[a:i]) + a
        right = np.flatnonzero(on_ground[i + 1:b]) + i + 1
        count = min(len(left), len(right))
        if count < 2:
            continue
        before, after = left[-count:][::-1], right[:count]
        slope = np.median((raw[after] - raw[before]) / (meters[after] - meters[before]))
        neighbors = np.r_[before, after]
        expected = np.median(raw[neighbors] - slope * (meters[neighbors] - meters[i]))
        if abs(raw[i] - expected) > SPIKE_DEVIATION_M:
            cleaned[i] = expected
    return cleaned


def _structure_blocks(spans, guard):
    blocks = []
    for span in spans:
        if blocks and span.start_m <= blocks[-1][1] + 2 * guard:
            blocks[-1] = (blocks[-1][0], max(blocks[-1][1], span.end_m))
        else:
            blocks.append((span.start_m, span.end_m))
    return blocks


def prepare_terrain(meters, raw, uncertain, structures, resolution):
    """Repair isolated centerline spikes and bridge gaps from the approach elevations."""
    window = max(150, 3 * resolution)
    guard = max(30, resolution / 2)
    on_ground = np.ones(len(meters), dtype=bool)
    for span in structures:
        on_ground &= (meters < span.start_m - guard) | (meters > span.end_m + guard)
    cleaned = _repair_spikes(meters, raw, uncertain, on_ground, window)
    if structures and not on_ground.any():
        raise ElevationUnavailable("No ground approaches outside the tagged structures")
    # Remove surface samples around structures before longitudinal smoothing.
    for start, end in _structure_blocks(structures, guard):
        left = np.flatnonzero(on_ground & (meters < start - guard))
        right = np.flatnonzero(on_ground & (meters > end + guard))
        preferred_left = left[(meters[left] >= start - window) & ~uncertain[left]]
        preferred_right = right[(meters[right] <= end + window) & ~uncertain[right]]
        anchors = np.r_[
            (preferred_left if len(preferred_left) else left)[-1:],
            (preferred_right if len(preferred_right) else right)[:1],
        ]
        if not len(anchors):
            raise ElevationUnavailable("No available approach elevation")
        affected = (meters >= start - guard) & (meters <= end + guard)
        cleaned[affected] = np.interp(meters[affected], meters[anchors], cleaned[anchors])
    smoothed = smooth_height(cleaned, meters[1] - meters[0], window)
    if structures:
        # Include actual entries and exits, even for structures shorter than one DEM sample.
        boundaries = [v for span in structures for v in (span.start_m, span.end_m)]
        expanded = np.unique(np.r_[meters, boundaries])
        profile = np.interp(expanded, meters, smoothed)
        for span in structures:
            inside = (expanded > span.start_m) & (expanded < span.end_m)
            ends = [span.start_m, span.end_m]
            profile[inside] = np.interp(expanded[inside], ends, np.interp(ends, meters, smoothed))
    else:
        expanded, profile = meters, smoothed
    return expanded, profile, (*_lateral_spans(meters, uncertain), *structures)
