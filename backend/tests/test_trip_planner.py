from dataclasses import replace
from types import SimpleNamespace

from app.api.errors import AppError
from app.services import trip_planner
from app.services.trip_planner import Point, Stop, _choose_path, _estimate_charging, _usable_power_kw, decode_polyline
from app.vehicles.catalog import get_catalog


def test_short_charge_cannot_skip_required_stop():
    distance = [
        [0, 100_000, 200_000],
        [float("inf"), 0, 100_000],
        [float("inf"), float("inf"), 0],
    ]
    duration = [
        [0, 3600, 7200],
        [float("inf"), 0, 3600],
        [float("inf"), float("inf"), 0],
    ]
    assert _choose_path(distance, duration, 50, 300) == [0, 1, 2]
    assert _choose_path(distance, duration, 80, 300) == [0, 2]
    assert _choose_path(distance, duration, 30, 300) is None


def test_neshan_polyline_coordinates():
    points = decode_polyline("_p~iF~ps|U_ulLnnqC_mqNvxq`@")
    assert points == [Point(38.5, -120.2), Point(40.7, -120.95), Point(43.252, -126.453)]


def test_charging_time_includes_effective_power_and_setup():
    energy, charging, stopped = _estimate_charging(84.8, 30, 90, 50)
    assert energy == 50.9
    assert charging == 82 * 60
    assert stopped == 87 * 60


def test_charging_power_respects_vehicle_limit_and_missing_station_power():
    vehicle = next(item for item in get_catalog().variants() if item.powertrain_type == "BEV")
    vehicle = replace(vehicle, dc_charge_limit_kw=40, ac_charge_limit_kw=3.3)
    assert _usable_power_kw(SimpleNamespace(standard="CCS_2", max_power_w=60_000), vehicle) == (40, False)
    assert _usable_power_kw(SimpleNamespace(standard="TYPE_2", max_power_w=None), vehicle) == (3.3, True)


def test_missing_vehicle_limit_is_marked_as_assumed_and_capped():
    vehicle = next(item for item in get_catalog().variants() if item.powertrain_type == "BEV")
    vehicle = replace(vehicle, dc_charge_limit_kw=None, ac_charge_limit_kw=None)
    assert _usable_power_kw(SimpleNamespace(standard="GBT_DC", max_power_w=120_000), vehicle) == (80, True)
    assert _usable_power_kw(SimpleNamespace(standard="TYPE_2", max_power_w=22_000), vehicle) == (11, True)


def test_plan_uses_road_matrix_when_detailed_route_is_rate_limited(monkeypatch):
    vehicle = next(item for item in get_catalog().variants() if item.powertrain_type == "BEV" and item.range_km == 400 and item.station_standards)
    origin, destination = Point(35.7, 51.4), Point(34.7, 50.8)
    stop = Stop("station", "ایستگاه آزمون", "station-test", Point(35.2, 51.1), 90_000, 500, 50, "unknown")
    calls = 0

    def direction(*_args, **_kwargs):
        nonlocal calls
        calls += 1
        if calls == 2:
            raise AppError(429, "Rate limit", "rate limited")
        return {"overview_polyline": {"points": "_p~iF~ps|U_ulLnnqC"}, "legs": [{"distance": {"value": 180_000}, "duration": {"value": 9000}}]}

    monkeypatch.setattr(trip_planner, "_direction", direction)
    monkeypatch.setattr(trip_planner, "_candidates", lambda *_args: [stop])
    monkeypatch.setattr(trip_planner, "_matrix", lambda *_args: (
        [[0, 90_000, 180_000], [float("inf"), 0, 90_000], [float("inf"), float("inf"), 0]],
        [[0, 4000, 9000], [float("inf"), 0, 4000], [float("inf"), float("inf"), 0]],
    ))
    result = trip_planner.plan_trip(None, origin, destination, vehicle.id, 45)
    assert result["status"] == "ok"
    assert result["route_includes_stops"] is False
    assert result["arrival_soc"] >= 10
    assert len(result["stops"]) == 1
    assert result["stops"][0]["departure_soc"] == 40
    assert result["stops"][0]["charging_duration_s"] > 0
    assert result["stops"][0]["stop_duration_s"] == result["stops"][0]["charging_duration_s"] + 300
    assert result["total_trip_duration_s"] == result["total_duration_s"] + result["total_stop_duration_s"]
