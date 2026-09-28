"""Province of a coordinate, from OpenStreetMap provincial boundaries.

Boundaries: hosseinhabibi2004/iran-geojson (OSM, ODbL). Persian names have the
«استان» prefix already removed.
"""

from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path

_DATA = Path(__file__).resolve().parent.parent / "data" / "iran-provinces.geojson"


def _point_in_ring(lng: float, lat: float, ring: list) -> bool:
    inside = False
    j = len(ring) - 1
    for i, point in enumerate(ring):
        xi, yi = point[0], point[1]
        xj, yj = ring[j][0], ring[j][1]
        if (yi > lat) != (yj > lat):
            cross = (xj - xi) * (lat - yi) / (yj - yi) + xi
            if lng < cross:
                inside = not inside
        j = i
    return inside


def _point_in_polygon(lng: float, lat: float, rings: list) -> bool:
    if not rings or not _point_in_ring(lng, lat, rings[0]):
        return False
    return all(not _point_in_ring(lng, lat, hole) for hole in rings[1:])


def _bbox(geometry: dict) -> tuple[float, float, float, float]:
    xs: list[float] = []
    ys: list[float] = []

    def walk(node) -> None:
        if node and isinstance(node[0], (int, float)):
            xs.append(node[0])
            ys.append(node[1])
            return
        for child in node:
            walk(child)

    walk(geometry["coordinates"])
    return min(xs), min(ys), max(xs), max(ys)


@lru_cache(maxsize=1)
def _provinces() -> tuple[tuple[str, tuple[float, float, float, float], dict], ...]:
    data = json.loads(_DATA.read_text(encoding="utf-8"))
    rows = []
    for feature in data["features"]:
        name = str(feature["properties"]["name:fa"]).strip()
        geometry = feature["geometry"]
        rows.append((name, _bbox(geometry), geometry))
    return tuple(rows)


def province_at(lat: float, lng: float) -> str | None:
    """Persian province name for a WGS84 point, or None when it is outside Iran."""
    for name, (west, south, east, north), geometry in _provinces():
        if not (south <= lat <= north and west <= lng <= east):
            continue
        polygons = geometry["coordinates"]
        if geometry["type"] == "Polygon":
            polygons = [polygons]
        if any(_point_in_polygon(lng, lat, rings) for rings in polygons):
            return name
    return None
