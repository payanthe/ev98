from __future__ import annotations

import math
from collections.abc import Callable
from dataclasses import dataclass
from itertools import pairwise

from sqlalchemy import select
from sqlalchemy.orm import Session
from sqlalchemy.orm import selectinload

from app.api.errors import AppError
from app.core.config import settings
from app.models.entities import ChargingPool, Connector, Evse, Location
from app.models.base import utcnow
from app.vehicles.catalog import VehicleVariant, get_catalog

from app.services.trip_energy import LegEnergy, TripEnergy
from app.services.trip_profile import chart_leg, chart_quality, chart_summary, map_leg
from app.services.trip_router import Point, RoadLeg, car_matrix, car_route, decode_polyline

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


def _projection(point: Point, route: list[Point]) -> tuple[float, float]:
    # Equirectangular projection is sufficient for candidate filtering; the graph supplies road distances.
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
    endpoint_buffer = min(5_000, max(200, route_m * .05))
    now = utcnow()
    for location in db.scalars(stmt).all():
        point = Point(float(location.latitude), float(location.longitude))
        progress, deviation = _projection(point, route)
        if deviation > 25_000 or progress < endpoint_buffer or progress > route_m - endpoint_buffer:
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


def _shortest_path(duration: list[list[float]], rejected: set[tuple[int, int]]) -> list[int] | None:
    n = len(duration)
    costs = [float("inf")] * n
    previous = [-1] * n
    costs[0] = 0
    for i in range(n - 1):
        if not math.isfinite(costs[i]):
            continue
        for j in range(i + 1, n):
            if not math.isfinite(duration[i][j]) or (i, j) in rejected:
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


def _choose_path(leg_for: Callable[[int, int], LegEnergy], duration: list[list[float]], start_soc: float) -> list[int] | None:
    rejected: set[tuple[int, int]] = set()
    # Each ranked path is the cheapest among all paths not yet ruled out.
    # Only an actual battery check can reject a leg, including legs with net regeneration.
    while (path := _shortest_path(duration, rejected)) is not None:
        for i, j in pairwise(path):
            departure = start_soc if i == 0 else MAX_DEPARTURE_SOC
            if not leg_for(i, j).reaches(departure, RESERVE_SOC):
                rejected.add((i, j))
                break
        else:
            return path
    return None


def _grade_status(profiles: list[LegEnergy], include_grade: bool) -> str:
    if not include_grade:
        return "disabled"
    if all(p.uses_grade for p in profiles):
        return "applied"
    return "partial" if any(p.uses_grade for p in profiles) else "unavailable"


def plan_trip(db: Session, origin: Point, destination: Point, vehicle_id: str, start_soc: float,
              *, include_grade: bool = True) -> dict:
    variant = get_catalog().get(vehicle_id)
    if variant is None:
        raise AppError(404, "Vehicle not found", "خودرو پیدا نشد.")
    if variant.powertrain_type not in {"BEV", "PHEV"} or not variant.range_km or not variant.station_standards:
        raise AppError(422, "Vehicle data incomplete", "برای این خودرو اطلاعات برد یا سوکت لازم برای برنامه‌ریزی موجود نیست.")
    effective_range = variant.range_km * REAL_RANGE_FACTOR
    battery_kwh = variant.battery_kwh_max or variant.battery_kwh_min
    energy = TripEnergy(effective_range * 1000, battery_kwh,
                        settings.offline_trip_dir / "elevation" if include_grade else None)
    direct = car_route([origin, destination])
    encoded = direct.polyline
    try:
        route = decode_polyline(encoded)
    except ValueError as exc:
        raise AppError(502, "Invalid route", "هندسهٔ مسیر محلی قابل خواندن نیست.") from exc
    direct_leg = direct.legs[0]
    direct_m = direct_leg.distance_m
    if len(route) < 2 or direct_m <= 0:
        raise AppError(422, "No route", "مسیر معتبری برای سفر پیدا نشد.")
    direct_profile = energy.for_leg(direct_leg)
    base = {
        "direct_distance_m": direct_m,
        "effective_range_km": round(effective_range),
        "direct_energy_kwh": energy.kwh(direct_profile.net_soc),
        "direct_battery_used_pct": round(start_soc - direct_profile.arrival(start_soc), 1),
        "direct_min_departure_soc": (
            round(RESERVE_SOC + direct_profile.peak_draw_soc, 2)
            if direct_profile.reaches(100, RESERVE_SOC) else None
        ),
    }

    def infeasible(reason: str) -> dict:
        return {**base, "status": "no_feasible_route", "reason": reason, "stops": [], "legs": [],
                "polyline": encoded, "grade_status": _grade_status([direct_profile], include_grade)}

    stops: list[Stop] = []
    if direct_profile.reaches(start_soc, RESERVE_SOC):
        path = [0, 1]
        final = direct
        profiles = [direct_profile]
    else:
        stops = _candidates(db, route, set(variant.station_standards), direct_m, variant)
        if not stops:
            return infeasible("ایستگاه شارژ سازگار در نزدیکی مسیر پیدا نشد.")
        unreachable = "با شارژ فعلی و ایستگاه‌های ثبت‌شده، مسیر قابل‌اطمینانی پیدا نشد."
        # Every leg starts at a prefix draw of zero, so even a descent cannot
        # satisfy the reserve if the starting battery is already below it.
        if start_soc < RESERVE_SOC - 1e-9:
            return infeasible(unreachable)
        points = [origin, *(stop.point for stop in stops), destination]
        distance, duration = car_matrix(points)
        last = len(points) - 1
        estimates = {(0, last): direct_profile}

        def leg_for(i: int, j: int) -> LegEnergy:
            if (i, j) not in estimates:
                profile = energy.flat(distance[i][j])
                if energy.covers(points[i]) and energy.covers(points[j]):
                    try:
                        profile = energy.for_leg(car_route([points[i], points[j]]).legs[0])
                    except AppError as exc:
                        if exc.status_code != 422:
                            raise
                        profile = energy.flat(math.inf)
                estimates[i, j] = profile
            return estimates[i, j]

        while True:
            path = _choose_path(leg_for, duration, start_soc)
            if path is None:
                return infeasible(unreachable)
            final = car_route([points[i] for i in path])
            profiles = [energy.for_leg(leg) for leg in final.legs]
            # Waypoint matching can change a leg. Recheck its actual profile before committing to a stop.
            failed = next((idx for idx, profile in enumerate(profiles)
                           if not profile.reaches(start_soc if idx == 0 else MAX_DEPARTURE_SOC, RESERVE_SOC)), None)
            if failed is None:
                break
            duration[path[failed]][path[failed + 1]] = math.inf
    soc = start_soc
    result_legs = []
    result_stops = []
    total_charging_seconds = 0
    total_stop_seconds = 0
    charging_time_complete = True
    chart_segments, chart_stops, quality_spans, map_legs = [], [], [], []
    structures_unchecked_m = 0
    distance_so_far = 0
    total_distance = sum(round(leg.distance_m) for leg in final.legs)
    chart_capacity = energy.battery_kwh if any(p.uses_grade for p in profiles) else None
    interval = max(250., total_distance / 600)
    for idx, (leg, profile) in enumerate(zip(final.legs, profiles, strict=True)):
        from_idx = path[idx]
        if idx > 0:
            needed_soc = profile.peak_draw_soc + RESERVE_SOC
            target_soc = max(soc, min(MAX_DEPARTURE_SOC, math.ceil(needed_soc - 1e-9)))
            station = stops[from_idx - 1]
            charge_kwh, charging_seconds, stop_seconds = _estimate_charging(battery_kwh, soc, target_soc, station.charging_power_kw or station.power_kw)
            if charging_seconds is None or stop_seconds is None:
                charging_time_complete = False
            else:
                total_charging_seconds += charging_seconds
                total_stop_seconds += stop_seconds
            result_stops.append({"id": station.id, "slug": station.slug, "name": station.name, "lat": station.point.lat, "lng": station.point.lng, "arrival_soc": round(soc), "departure_soc": round(target_soc), "power_kw": station.power_kw, "charging_power_kw": station.charging_power_kw or station.power_kw, "charging_power_assumed": station.charging_power_assumed, "charge_added_kwh": charge_kwh, "charging_duration_s": charging_seconds, "stop_duration_s": stop_seconds, "availability": station.availability})
            if chart_capacity:
                chart_stops.append({
                    "name": station.name, "distance_m": distance_so_far,
                    "arrival_soc": round(soc, 2), "departure_soc": round(target_soc, 2),
                    "charge_kwh": charge_kwh,
                })
            soc = target_soc
        arrival = profile.arrival(soc)
        if chart_capacity:
            chart_segments.extend(chart_leg(leg, profile, distance_so_far, soc, chart_capacity, interval))
            styled_leg = map_leg(leg, profile, soc, chart_capacity)
            if styled_leg:
                map_legs.append(styled_leg)
            quality_spans.extend(chart_quality(leg, profile, distance_so_far))
            if profile.terrain and not profile.terrain.structures_checked:
                structures_unchecked_m += round(leg.distance_m)
        distance_so_far += round(leg.distance_m)
        result_legs.append({"distance_m": round(leg.distance_m), "duration_s": round(leg.duration_s),
                            "departure_soc": round(soc), "arrival_soc": round(arrival),
                            "energy_kwh": energy.kwh(soc - arrival), "grade_applied": profile.uses_grade})
        soc = arrival
    driving_seconds = sum(leg["duration_s"] for leg in result_legs)
    energy_kwh = round(sum(leg["energy_kwh"] for leg in result_legs), 3) if energy.battery_kwh else None
    elevation_profile = (
        chart_summary(chart_segments, chart_stops, total_distance, quality_spans, structures_unchecked_m)
        if chart_segments else None
    )
    if elevation_profile:
        elevation_profile["map_legs"] = map_legs
    return {**base, "status": "ok", "reason": None, "energy_kwh": energy_kwh,
            "grade_status": _grade_status(profiles, include_grade),
            "elevation_profile": elevation_profile, "total_distance_m": total_distance, "total_duration_s": driving_seconds, "total_charging_duration_s": total_charging_seconds if charging_time_complete else None, "total_stop_duration_s": total_stop_seconds if charging_time_complete else None, "total_trip_duration_s": driving_seconds + total_stop_seconds if charging_time_complete else None, "arrival_soc": round(soc, 1), "stops": result_stops, "legs": result_legs, "polyline": final.polyline, "route_includes_stops": True, "directions": final.steps}
