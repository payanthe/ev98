from dataclasses import replace
from types import SimpleNamespace

import numpy as np

from app.services import trip_planner
from app.services.trip_planner import Point, Stop, _choose_path, _estimate_charging, _usable_power_kw, decode_polyline
from app.services.trip_energy import LegEnergy, TerrainTrace, TripEnergy
from app.services.trip_profile import chart_leg, chart_summary, map_leg
from app.services.trip_router import RoadLeg, RoadRoute
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
    energy = TripEnergy(300_000, None, None)

    def flat(i, j):
        return energy.flat(distance[i][j])

    assert _choose_path(flat, duration, 50) == [0, 1, 2]
    assert _choose_path(flat, duration, 80) == [0, 2]
    assert _choose_path(flat, duration, 30) is None


def test_polyline5_coordinates():
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


def test_plan_routes_through_the_chosen_charge_stop(monkeypatch):
    vehicle = next(item for item in get_catalog().variants() if item.powertrain_type == "BEV" and item.range_km == 400 and item.station_standards)
    origin, destination = Point(35.7, 51.4), Point(34.7, 50.8)
    stop = Stop("station", "ایستگاه آزمون", "station-test", Point(35.2, 51.1), 90_000, 500, 50, "unknown")
    direct_polyline = "_p~iF~ps|U_ulLnnqC"
    stop_polyline = "_p~iF~ps|U_ulLnnqC_mqNvxq`@"
    selected_points = []

    def route(points):
        selected_points.append(points)
        if len(points) == 2:
            return RoadRoute(direct_polyline, (RoadLeg(180_000, 9000),))
        return RoadRoute(stop_polyline, (RoadLeg(90_000, 4000), RoadLeg(90_000, 5000)),
                         ({"type": "depart"},))

    monkeypatch.setattr(trip_planner, "car_route", route)
    monkeypatch.setattr(trip_planner, "_candidates", lambda *_args: [stop])
    monkeypatch.setattr(trip_planner, "car_matrix", lambda *_args: (
        [[0, 90_000, 180_000], [float("inf"), 0, 90_000], [float("inf"), float("inf"), 0]],
        [[0, 4000, 9000], [float("inf"), 0, 5000], [float("inf"), float("inf"), 0]],
    ))
    result = trip_planner.plan_trip(None, origin, destination, vehicle.id, 45, include_grade=False)
    assert selected_points == [[origin, destination], [origin, stop.point, destination]]
    assert result["status"] == "ok"
    assert result["route_includes_stops"] is True
    assert result["polyline"] == stop_polyline
    assert result["directions"][0]["type"] == "depart"
    assert result["arrival_soc"] >= 10
    assert result["direct_battery_used_pct"] == 60
    assert len(result["stops"]) == 1
    assert result["stops"][0]["departure_soc"] == 40
    assert result["stops"][0]["charging_duration_s"] > 0
    assert result["stops"][0]["stop_duration_s"] == result["stops"][0]["charging_duration_s"] + 300
    assert result["total_trip_duration_s"] == result["total_duration_s"] + result["total_stop_duration_s"]

    direct_result = trip_planner.plan_trip(None, origin, destination, vehicle.id, 80, include_grade=False)
    assert direct_result["stops"] == []
    assert direct_result["arrival_soc"] == 20
    assert direct_result["direct_battery_used_pct"] == 60

    monkeypatch.setattr(trip_planner, "_candidates", lambda *_args: [])
    infeasible = trip_planner.plan_trip(None, origin, destination, vehicle.id, 45, include_grade=False)
    assert infeasible["status"] == "no_feasible_route"
    assert infeasible["direct_battery_used_pct"] == 60


def test_grade_requires_stop_when_later_regen_would_hide_reserve_violation():
    duration = [[0, 400, 800], [float("inf"), 0, 500], [float("inf"), float("inf"), 0]]
    grades = {
        (0, 1): LegEnergy(3, 3, uses_grade=True),
        (0, 2): LegEnergy(-1, 7, -1, 7, uses_grade=True),
        (1, 2): LegEnergy(-4, 4, -4, 4, uses_grade=True),
    }
    assert grades[0, 2].arrival(15) == 16
    assert _choose_path(lambda i, j: grades[i, j], duration, 15) == [0, 1, 2]


def test_planner_profiles_only_the_legs_needed_to_verify_the_cheapest_path():
    unreachable = float("inf")
    duration = [
        [0, 100, 500, unreachable],
        [unreachable, 0, 300, 100],
        [unreachable, unreachable, 0, 500],
        [unreachable, unreachable, unreachable, 0],
    ]
    checked = []

    def profile(i, j):
        checked.append((i, j))
        return LegEnergy(15, 15)

    assert _choose_path(profile, duration, 50) == [0, 1, 3]
    assert checked == [(0, 1), (1, 3)]


def test_recuperation_is_capped_at_full_charge_before_a_later_climb():
    leg = LegEnergy(4, 4, -6, 10, uses_grade=True)
    assert leg.arrival(90) == 86
    assert leg.arrival(98) == 90
    assert leg.arrival(100) == 90


def test_elevation_chart_matches_final_soc_after_regeneration_cap():
    trace = TerrainTrace(
        meters=np.array([0., 100., 200.]),
        heights=np.array([150., 130., 160.]),
        uphill_m=np.array([0., 100.]),
        downhill_m=np.array([100., 0.]),
        draw_kwh=np.array([1., 4.]),
        regen_kwh=np.array([3., 0.]),
        resolution_m=90,
    )
    leg = RoadLeg(200., 20.)
    profile = LegEnergy(4., 4., -4., 8., uses_grade=True, terrain=trace)
    segments = chart_leg(leg, profile, 0, 99., 50., 100.)
    result = chart_summary(segments, [], 200)
    assert segments[0]["end_soc"] == 100
    assert segments[-1]["end_soc"] == profile.arrival(99.) == 92
    assert result["uphill_m"] == result["downhill_m"] == 100
    assert result["draw_kwh"] - result["regen_kwh"] == 3.5
    assert result["regen_kwh"] == 1.5


def test_map_distinguishes_downhill_consumption_from_battery_recovery():
    trace = TerrainTrace(
        meters=np.array([0., 100., 200., 300.]),
        heights=np.array([150., 135., 130., 145.]),
        uphill_m=np.array([0., 0., 100.]),
        downhill_m=np.array([100., 100., 0.]),
        draw_kwh=np.array([0., 1., 2.]),
        regen_kwh=np.array([1., 0., 0.]),
        resolution_m=90,
    )
    shape = (Point(35.0, 51.0), Point(35.00075, 51.00225), Point(35.00125, 51.00175))
    leg = RoadLeg(300., 30., shape)
    profile = LegEnergy(4., 4., -2., 6., uses_grade=True, terrain=trace)

    normal = map_leg(leg, profile, 90., 50.)
    full = map_leg(leg, profile, 100., 50.)
    assert decode_polyline(normal["polyline"]) == list(shape)
    assert normal["energy"] == [(100., "recovery"), (300., "consumption")]
    assert full["energy"] == [(100., "neutral"), (300., "consumption")]
    assert full["slope"] == normal["slope"] == [(200., "downhill"), (300., "uphill")]
