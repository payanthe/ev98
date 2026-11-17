"""Automobile directions and distance matrices over a local Valhalla graph."""
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from threading import Lock

from valhalla import Actor, ValhallaError, get_config

from app.api.errors import AppError
from app.core.config import settings


@dataclass(frozen=True)
class Point:
    lat: float
    lng: float


@dataclass(frozen=True)
class RoadLeg:
    distance_m: float
    duration_s: float
    shape: tuple[Point, ...] = ()


@dataclass(frozen=True)
class RoadRoute:
    polyline: str
    legs: tuple[RoadLeg, ...]
    steps: tuple[dict, ...] = ()


_actor_lock = Lock()


def require_graph(graph: Path) -> None:
    if not next(graph.rglob("*.gph"), None):
        raise AppError(503, "Route graph unavailable", "گراف محلی مسیریابی خودرو آماده نیست.")


@lru_cache(maxsize=1)
def _actor(graph: Path) -> Actor:
    require_graph(graph)
    config = get_config(tile_dir=graph, tile_extract="")
    config["mjolnir"].pop("traffic_extract", None)
    config["service_limits"]["auto"]["max_matrix_distance"] = 2_500_000
    return Actor(config)


def _location(point: Point) -> dict:
    return {"lat": point.lat, "lon": point.lng, "search_cutoff": 4_000}


def _engine_request(action: str, payload: dict) -> dict:
    try:
        with _actor_lock:
            engine = _actor(settings.offline_trip_dir / "valhalla_tiles")
            return getattr(engine, action)({"costing": "auto", **payload})
    except ValhallaError as exc:
        if exc.code in {154, 170, 171, 172, 173, 442}:
            raise AppError(422, "No car route", "برای نقطه‌های انتخاب‌شده مسیر خودرو پیدا نشد.") from exc
        raise AppError(503, "Local router unavailable", "موتور محلی مسیریابی خودرو در دسترس نیست.") from exc
    except (OSError, RuntimeError) as exc:
        raise AppError(503, "Local router unavailable", "موتور محلی مسیریابی خودرو در دسترس نیست.") from exc


def decode_polyline(encoded: str, *, precision: int = 5) -> list[Point]:
    lat = lng = index = 0
    points: list[Point] = []
    scale = 10**precision
    while index < len(encoded):
        values = []
        for _ in range(2):
            shift = result = 0
            while True:
                if index >= len(encoded):
                    raise ValueError("Invalid polyline")
                code = ord(encoded[index]) - 63
                index += 1
                result |= (code & 0x1F) << shift
                shift += 5
                if code < 0x20:
                    break
            values.append((result >> 1) ^ -(result & 1))
        lat += values[0]
        lng += values[1]
        points.append(Point(lat / scale, lng / scale))
    return points


def encode_polyline(points: tuple[Point, ...]) -> str:
    lat = lng = 0
    encoded = []
    for point in points:
        next_lat, next_lng = round(point.lat * 100_000), round(point.lng * 100_000)
        for delta in (next_lat - lat, next_lng - lng):
            code = ~(delta << 1) if delta < 0 else delta << 1
            while code >= 0x20:
                encoded.append(chr(((code & 0x1F) | 0x20) + 63))
                code >>= 5
            encoded.append(chr(code + 63))
        lat, lng = next_lat, next_lng
    return "".join(encoded)


def _leg_shape(steps: list[dict]) -> tuple[Point, ...]:
    points: list[Point] = []
    for step in steps:
        segment = decode_polyline(step["geometry"])
        points.extend(segment[1:] if points and segment and points[-1] == segment[0] else segment)
    return tuple(points)


def car_route(points: list[Point]) -> RoadRoute:
    result = _engine_request("route", {
        "locations": [_location(p) for p in points],
        "format": "osrm",
        "shape_format": "polyline5",
        "directions_type": "maneuvers",
    })
    try:
        route = result["routes"][0]
        polyline = route["geometry"]
        legs = tuple(
            RoadLeg(leg["distance"], leg["duration"], _leg_shape(leg["steps"]))
            for leg in route["legs"]
        )
        if not isinstance(polyline, str) or not polyline or len(legs) != len(points) - 1:
            raise ValueError("Incomplete route")
        steps = tuple(
            {
                "type": step["maneuver"]["type"],
                "modifier": step["maneuver"].get("modifier"),
                "exit": step["maneuver"].get("exit"),
                "road": step.get("name") or step.get("rotary_name") or step.get("destinations"),
                "distance_m": round(step["distance"]),
            }
            for leg in route["legs"] for step in leg.get("steps", [])
        )
        return RoadRoute(polyline, legs, steps)
    except (KeyError, IndexError, TypeError, ValueError) as exc:
        raise AppError(502, "Invalid local route", "هندسه یا بخش‌های مسیر محلی قابل خواندن نیست.") from exc


def car_matrix(points: list[Point]) -> tuple[list[list[float]], list[list[float]]]:
    locations = [_location(p) for p in points]
    size = len(points)
    distance = [[float("inf")] * size for _ in points]
    duration = [[float("inf")] * size for _ in points]
    result = _engine_request("matrix", {"sources": locations, "targets": locations, "units": "kilometers"})
    for row in result["sources_to_targets"]:
        for cell in row:
            i, j = cell["from_index"], cell["to_index"]
            if cell["distance"] is not None and cell["time"] is not None:
                distance[i][j] = cell["distance"] * 1000
                duration[i][j] = cell["time"]
    return distance, duration
