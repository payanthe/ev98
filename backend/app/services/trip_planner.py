from __future__ import annotations

import json
import math
from dataclasses import dataclass

import httpx
from sqlalchemy import select
from sqlalchemy.orm import Session
from sqlalchemy.orm import selectinload

from app.api.errors import AppError
from app.core.config import settings
from app.models.entities import ChargingPool, Connector, Evse, Location
from app.models.base import utcnow
from app.vehicles.catalog import VehicleVariant, get_catalog

BASE = "https://api.neshan.org"
RESERVE_SOC = 10.0
MAX_DEPARTURE_SOC = 95.0
REAL_RANGE_FACTOR = 0.75
CHARGE_POWER_FACTOR = 0.75
CHARGE_SETUP_SECONDS = 5 * 60
DEFAULT_DC_POWER_KW = 50.0
DEFAULT_AC_POWER_KW = 7.0
ASSUMED_VEHICLE_DC_LIMIT_KW = 80.0
ASSUMED_VEHICLE_AC_LIMIT_KW = 11.0
DC_STANDARDS = {"CCS_2", "GBT_DC", "CHADEMO"}


@dataclass(frozen=True)
class Point:
    lat: float
    lng: float


@dataclass(frozen=True)
class Stop:
    id: str
    name: str
    slug: str
    point: Point
    progress_m: float
    deviation_m: float
    power_kw: float | None
    availability: str
    charging_power_kw: float | None = None
    charging_power_assumed: bool = False


def _usable_power_kw(connector: Connector, vehicle: VehicleVariant) -> tuple[float, bool]:
    is_dc = connector.standard in DC_STANDARDS
    recorded_kw = (connector.max_power_w or 0) / 1000
    assumed = recorded_kw <= 0
    station_kw = recorded_kw if recorded_kw > 0 else (DEFAULT_DC_POWER_KW if is_dc else DEFAULT_AC_POWER_KW)
    vehicle_limit = vehicle.dc_charge_limit_kw if is_dc else vehicle.ac_charge_limit_kw
    if vehicle_limit is None or vehicle_limit <= 0:
        vehicle_limit = ASSUMED_VEHICLE_DC_LIMIT_KW if is_dc else ASSUMED_VEHICLE_AC_LIMIT_KW
        assumed = True
    station_kw = min(station_kw, vehicle_limit)
    return station_kw, assumed


def _estimate_charging(battery_kwh: float | None, arrival_soc: float, departure_soc: float, power_kw: float | None) -> tuple[float | None, int | None, int | None]:
    if battery_kwh is None or battery_kwh <= 0 or power_kw is None or power_kw <= 0:
        return None, None, None
    energy_kwh = battery_kwh * max(0, departure_soc - arrival_soc) / 100
    charging_seconds = math.ceil(energy_kwh / (power_kw * CHARGE_POWER_FACTOR) * 60) * 60
    stop_seconds = charging_seconds + CHARGE_SETUP_SECONDS if energy_kwh > 0 else 0
    return round(energy_kwh, 1), charging_seconds, stop_seconds


def _get(client: httpx.Client, path: str, params: dict) -> dict:
    if not settings.neshan_api_key:
        raise AppError(503, "Neshan not configured", "کلید سرویس نشان در سرور تنظیم نشده است.")
    try:
        response = client.get(f"{BASE}{path}", params=params, headers={"Api-Key": settings.neshan_api_key})
        if response.status_code == 482:
            raise AppError(429, "Neshan rate limit", "تعداد درخواست‌های نشان در این دقیقه به سقف رسید. یک دقیقه دیگر دوباره تلاش کنید.")
        if response.status_code in {480, 483, 484, 485}:
            raise AppError(503, "Neshan access denied", "دسترسی این کلید نشان به سرویس موردنیاز فعال نیست.")
        response.raise_for_status()
        return response.json()
    except (httpx.HTTPError, ValueError) as exc:
        raise AppError(502, "Neshan unavailable", "ارتباط با سرویس نشان برقرار نشد. کمی بعد دوباره تلاش کنید.") from exc


def search_places(query: str) -> list[dict]:
    with httpx.Client(timeout=12) as client:
        data = _get(client, "/geocoding/v1", {"json": json.dumps({"address": query}, ensure_ascii=False)})
    return [
        {"title": query, "address": "، ".join(part for part in [item.get("province"), item.get("city"), item.get("neighbourhood"), f"بخش نامشخص: {item['unMatchedTerm']}" if item.get("unMatchedTerm") else None] if part), "lat": item["location"]["latitude"], "lng": item["location"]["longitude"]}
        for item in data.get("items", [])[:5]
        if item.get("location", {}).get("latitude") is not None and item.get("location", {}).get("longitude") is not None
    ]


def reverse_place(point: Point) -> dict:
    with httpx.Client(timeout=12) as client:
        data = _get(client, "/v5/reverse", {"lat": point.lat, "lng": point.lng})
    address = data.get("formatted_address") or data.get("city") or "موقعیت انتخاب‌شده روی نقشه"
    return {"title": address, "address": address, "lat": point.lat, "lng": point.lng}


def decode_polyline(encoded: str) -> list[Point]:
    lat = lng = index = 0
    points: list[Point] = []
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
        points.append(Point(lat / 1e5, lng / 1e5))
    return points


def _haversine(a: Point, b: Point) -> float:
    lat1, lat2 = math.radians(a.lat), math.radians(b.lat)
    dlat, dlng = lat2 - lat1, math.radians(b.lng - a.lng)
    h = math.sin(dlat / 2) ** 2 + math.cos(lat1) * math.cos(lat2) * math.sin(dlng / 2) ** 2
    return 6371000 * 2 * math.asin(min(1, math.sqrt(h)))


def _projection(point: Point, route: list[Point]) -> tuple[float, float]:
    # Equirectangular projection is sufficient for candidate filtering; road distances come from Neshan.
    scale = math.cos(math.radians(point.lat))
    px, py = point.lng * scale * 111_000, point.lat * 111_000
    progress = best_progress = 0.0
    best = float("inf")
    for a, b in zip(route, route[1:]):
        ax, ay, bx, by = a.lng * scale * 111_000, a.lat * 111_000, b.lng * scale * 111_000, b.lat * 111_000
        dx, dy = bx - ax, by - ay
        length2 = dx * dx + dy * dy
        fraction = max(0.0, min(1.0, ((px - ax) * dx + (py - ay) * dy) / length2)) if length2 else 0.0
        distance = math.hypot(px - ax - fraction * dx, py - ay - fraction * dy)
        if distance < best:
            best = distance
            best_progress = progress + math.sqrt(length2) * fraction
        progress += math.sqrt(length2)
    return best_progress, best


def _candidates(db: Session, route: list[Point], standards: set[str], route_m: float, vehicle: VehicleVariant) -> list[Stop]:
    if not route or not standards:
        return []
    pad = 0.32
    stmt = (
        select(Location)
        .join(ChargingPool, ChargingPool.location_id == Location.id)
        .join(Evse, Evse.pool_id == ChargingPool.id)
        .join(Connector, Connector.evse_id == Evse.id)
        .where(
            Location.deleted_at.is_(None), Location.publish_status == "published",
            Location.is_public.is_(True), Evse.withdrawn_at.is_(None),
            Connector.standard.in_(standards),
            Location.latitude.between(min(p.lat for p in route) - pad, max(p.lat for p in route) + pad),
            Location.longitude.between(min(p.lng for p in route) - pad, max(p.lng for p in route) + pad),
        )
        .distinct()
        .limit(3000)
        .options(selectinload(Location.pools).selectinload(ChargingPool.evses).selectinload(Evse.connectors))
    )
    stops: list[Stop] = []
    now = utcnow()
    for location in db.scalars(stmt).all():
        point = Point(float(location.latitude), float(location.longitude))
        progress, deviation = _projection(point, route)
        if deviation > 25_000 or progress < 5_000 or progress > route_m - 5_000:
            continue
        compatible = [
            connector for pool in location.pools for evse in pool.evses
            if evse.withdrawn_at is None and evse.status != "UNAVAILABLE"
            for connector in evse.connectors
            if connector.standard in standards and connector.status != "UNAVAILABLE"
        ]
        if not compatible:
            continue
        power = max((c.max_power_w or 0 for c in compatible), default=0) / 1000 or None
        charging_power, power_assumed = max((_usable_power_kw(c, vehicle) for c in compatible), key=lambda item: item[0])
        has_fresh_available = any(
            (c.status == "AVAILABLE" or (c.status is None and c.evse.status == "AVAILABLE"))
            and c.evse.status_expires_at is not None and c.evse.status_expires_at > now
            for c in compatible
        )
        stops.append(Stop(str(location.id), location.canonical_name_fa, location.slug, point, progress, deviation, power, "available" if has_fresh_available else "unknown", charging_power, power_assumed))
    # Retain candidates all along the route, including sparse stretches.
    bins: dict[int, list[Stop]] = {}
    for stop in stops:
        bins.setdefault(int(stop.progress_m // 50_000), []).append(stop)
    selected = []
    for group in bins.values():
        closest = min(group, key=lambda s: s.deviation_m)
        strongest = max(group, key=lambda s: (float(s.charging_power_kw or 0), -s.deviation_m))
        selected.append(closest)
        if strongest.id != closest.id:
            selected.append(strongest)
    selected.sort(key=lambda s: s.progress_m)
    if len(selected) > 8:
        selected = [selected[round(i * (len(selected) - 1) / 7)] for i in range(8)]
    return selected


def _direction(client: httpx.Client, origin: Point, destination: Point, waypoints: list[Point] | None = None) -> dict:
    params = {"type": "car", "origin": f"{origin.lat},{origin.lng}", "destination": f"{destination.lat},{destination.lng}"}
    if waypoints:
        params["waypoints"] = "|".join(f"{p.lat},{p.lng}" for p in waypoints)
    data = _get(client, "/v4/direction", params)
    routes = data.get("routes") or []
    if not routes:
        raise AppError(422, "No route", "نشان برای این مبدأ و مقصد مسیر رانندگی پیدا نکرد.")
    return routes[0]


def _matrix(client: httpx.Client, points: list[Point]) -> tuple[list[list[float]], list[list[float]]]:
    size = len(points)
    distance = [[float("inf")] * size for _ in range(size)]
    duration = [[float("inf")] * size for _ in range(size)]
    data = _get(client, "/v1/distance-matrix/no-traffic", {
        "type": "car",
        "origins": "|".join(f"{p.lat},{p.lng}" for p in points),
        "destinations": "|".join(f"{p.lat},{p.lng}" for p in points),
    })
    for row_index, row in enumerate(data.get("rows", [])):
        for col_index, element in enumerate(row.get("elements", [])):
            if row_index < size and col_index < size and element.get("status") == "Ok":
                distance[row_index][col_index] = float(element["distance"]["value"])
                duration[row_index][col_index] = float(element["duration"]["value"])
    return distance, duration


def _choose_path(distance: list[list[float]], duration: list[list[float]], start_soc: float, range_km: float) -> list[int] | None:
    n = len(distance)
    costs = [float("inf")] * n
    previous = [-1] * n
    costs[0] = 0
    for i in range(n - 1):
        if not math.isfinite(costs[i]):
            continue
        usable_soc = (start_soc if i == 0 else MAX_DEPARTURE_SOC) - RESERVE_SOC
        for j in range(i + 1, n):
            leg = distance[i][j]
            if not math.isfinite(leg) or leg / (range_km * 1000) * 100 > usable_soc:
                continue
            # Road time plus a modest charging-stop penalty. Charging times are estimated below.
            cost = costs[i] + duration[i][j] + (1800 if j < n - 1 else 0)
            if cost < costs[j]:
                costs[j], previous[j] = cost, i
    if not math.isfinite(costs[-1]):
        return None
    path = []
    node = n - 1
    while node >= 0:
        path.append(node)
        node = previous[node]
    return path[::-1]


def plan_trip(db: Session, origin: Point, destination: Point, vehicle_id: str, start_soc: float) -> dict:
    variant = get_catalog().get(vehicle_id)
    if variant is None:
        raise AppError(404, "Vehicle not found", "خودرو پیدا نشد.")
    if variant.powertrain_type not in {"BEV", "PHEV"} or not variant.range_km or not variant.station_standards:
        raise AppError(422, "Vehicle data incomplete", "برای این خودرو اطلاعات برد یا سوکت لازم برای برنامه‌ریزی موجود نیست.")
    effective_range = variant.range_km * REAL_RANGE_FACTOR
    with httpx.Client(timeout=20) as client:
        direct = _direction(client, origin, destination)
        encoded = direct.get("overview_polyline", {}).get("points", "")
        try:
            route = decode_polyline(encoded)
        except ValueError as exc:
            raise AppError(502, "Invalid route", "هندسهٔ مسیر نشان قابل خواندن نیست.") from exc
        direct_m = sum(leg["distance"]["value"] for leg in direct.get("legs", []))
        if len(route) < 2 or direct_m <= 0:
            raise AppError(422, "No route", "مسیر معتبری برای سفر پیدا نشد.")
        if direct_m / (effective_range * 1000) * 100 <= start_soc - RESERVE_SOC:
            stops: list[Stop] = []
            points = [origin, destination]
            distance = [[0, direct_m], [float("inf"), 0]]
            duration = [[0, sum(leg["duration"]["value"] for leg in direct["legs"])], [float("inf"), 0]]
            path = [0, 1]
            final = direct
        else:
            stops = _candidates(db, route, set(variant.station_standards), direct_m, variant)
            points = [origin] + [s.point for s in stops] + [destination]
            if len(points) <= 2:
                return {"status": "no_feasible_route", "reason": "ایستگاه شارژ سازگار در نزدیکی مسیر پیدا نشد.", "direct_distance_m": direct_m, "effective_range_km": round(effective_range), "stops": [], "legs": [], "polyline": encoded}
            distance, duration = _matrix(client, points)
            path = _choose_path(distance, duration, start_soc, effective_range)
            if path is None:
                return {"status": "no_feasible_route", "reason": "با شارژ فعلی و ایستگاه‌های ثبت‌شده، مسیر قابل‌اطمینانی پیدا نشد.", "direct_distance_m": direct_m, "effective_range_km": round(effective_range), "stops": [], "legs": [], "polyline": encoded}
            try:
                final = _direction(client, origin, destination, [points[i] for i in path[1:-1]])
                route_includes_stops = True
            except AppError as exc:
                if exc.status_code != 429:
                    raise
                # The matrix already contains road distances for every chosen leg.
                # Keep the direct overview line when the detailed route is rate limited.
                final = {"overview_polyline": {"points": encoded}, "legs": [
                    {"distance": {"value": distance[a][b]}, "duration": {"value": duration[a][b]}}
                    for a, b in zip(path, path[1:])
                ]}
                route_includes_stops = False
        if not stops:
            route_includes_stops = True
        final_legs = final.get("legs", [])
        if len(final_legs) != len(path) - 1:
            raise AppError(502, "Invalid route", "بخش‌های مسیر نهایی نشان با توقف‌ها مطابقت ندارند.")
        soc = start_soc
        result_legs = []
        result_stops = []
        total_charging_seconds = 0
        total_stop_seconds = 0
        charging_time_complete = True
        battery_kwh = variant.battery_kwh_max or variant.battery_kwh_min
        for idx, leg in enumerate(final_legs):
            from_idx, to_idx = path[idx], path[idx + 1]
            used_soc = leg["distance"]["value"] / (effective_range * 1000) * 100
            if idx > 0:
                needed_soc = used_soc + RESERVE_SOC
                target_soc = max(soc, min(MAX_DEPARTURE_SOC, math.ceil(needed_soc)))
                if target_soc < needed_soc:
                    return {"status": "no_feasible_route", "reason": "مسافت واقعی یکی از بخش‌های مسیر از برد ایمن خودرو بیشتر است.", "direct_distance_m": direct_m, "effective_range_km": round(effective_range), "stops": [], "legs": [], "polyline": encoded}
                station = stops[from_idx - 1]
                charge_kwh, charging_seconds, stop_seconds = _estimate_charging(battery_kwh, soc, target_soc, station.charging_power_kw or station.power_kw)
                if charging_seconds is None or stop_seconds is None:
                    charging_time_complete = False
                else:
                    total_charging_seconds += charging_seconds
                    total_stop_seconds += stop_seconds
                result_stops.append({"id": station.id, "slug": station.slug, "name": station.name, "lat": station.point.lat, "lng": station.point.lng, "arrival_soc": round(soc), "departure_soc": round(target_soc), "power_kw": station.power_kw, "charging_power_kw": station.charging_power_kw or station.power_kw, "charging_power_assumed": station.charging_power_assumed, "charge_added_kwh": charge_kwh, "charging_duration_s": charging_seconds, "stop_duration_s": stop_seconds, "availability": station.availability})
                soc = target_soc
            arrival = soc - used_soc
            if arrival < RESERVE_SOC - 0.01:
                return {"status": "no_feasible_route", "reason": "مسافت واقعی مسیر با حاشیهٔ شارژ ایمن قابل پیمودن نیست.", "direct_distance_m": direct_m, "effective_range_km": round(effective_range), "stops": [], "legs": [], "polyline": encoded}
            result_legs.append({"distance_m": round(leg["distance"]["value"]), "duration_s": round(leg["duration"]["value"]), "departure_soc": round(soc), "arrival_soc": round(arrival)})
            soc = arrival
        driving_seconds = sum(leg["duration_s"] for leg in result_legs)
        return {"status": "ok", "reason": None, "direct_distance_m": direct_m, "total_distance_m": sum(leg["distance_m"] for leg in result_legs), "total_duration_s": driving_seconds, "total_charging_duration_s": total_charging_seconds if charging_time_complete else None, "total_stop_duration_s": total_stop_seconds if charging_time_complete else None, "total_trip_duration_s": driving_seconds + total_stop_seconds if charging_time_complete else None, "effective_range_km": round(effective_range), "arrival_soc": round(soc), "stops": result_stops, "legs": result_legs, "polyline": final.get("overview_polyline", {}).get("points", ""), "route_includes_stops": route_includes_stops}
