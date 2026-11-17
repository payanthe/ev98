# /// script
# requires-python = ">=3.12"
# dependencies = ["pyvalhalla==3.9.1", "rasterio", "numpy", "matplotlib"]
# ///
"""Compare flat-road and grade-aware battery estimates using locally stored data."""

import argparse
import csv
import json
from dataclasses import asdict
from pathlib import Path
import subprocess
import sys

import matplotlib
import numpy as np
from valhalla import Actor, get_config

matplotlib.use("Agg")
from matplotlib import pyplot as plt

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))
from app.services.elevation import (
    SAMPLE_M, SMOOTH_M, VEHICLE, battery_energy, distance_m, read_elevations, resample, smooth_height,
)


# Coordinates are (longitude, latitude). Valhalla snaps these to drivable roads.
ROUTES = {
    "city": (("Azadi", (51.3381, 35.6997)), ("Tajrish", (51.4289, 35.8069)), 45),
    "mountain": (("Fasham", (51.5282, 35.9303)), ("Shemshak", (51.4937, 36.0084)), 50),
}
DEFAULT_OUTPUT = Path(__file__).resolve().parents[1] / "outputs" / "elevation-pilot"


def get_route(actor, origin, destination):
    response = actor.route({
        "locations": [{"lon": lon, "lat": lat} for lon, lat in (origin, destination)],
        "costing": "auto",
        "format": "osrm",
        "shape_format": "geojson",
        "units": "kilometers",
    })
    route = response["routes"][0]
    shape = np.asarray(route["geometry"]["coordinates"])
    return shape, route["distance"]


def evaluate_route(actor, output, dem_tiles, kind, origin, destination, speed):
    start_name, start_coord = origin
    end_name, end_coord = destination
    shape, router_distance = get_route(actor, start_coord, end_coord)
    distance, points = resample(shape)
    if abs(distance[-1] - router_distance) > 0.02 * router_distance:
        raise ValueError(f"Route geometry and Valhalla mileage disagree for {start_name} to {end_name}")
    raw = read_elevations(dem_tiles, points)
    ds = np.diff(distance)
    smoothed = smooth_height(raw, ds[0], SMOOTH_M)
    dh = np.diff(smoothed)
    flat = battery_energy(ds, np.zeros_like(dh), speed)
    graded = battery_energy(ds, dh, speed)
    route_name = f"{start_name.lower()}-{end_name.lower()}"
    with (output / f"{route_name}.csv").open("w", newline="") as file:
        writer = csv.writer(file)
        writer.writerow(["distance_m", "longitude", "latitude", "raw_elevation_m",
                         "smoothed_elevation_m", "net_flat_kwh", "net_with_grade_kwh"])
        for meter, point, original, filtered, flat_kwh, graded_kwh in zip(
            distance, points, raw, smoothed, np.r_[0, flat.cumsum()], np.r_[0, graded.cumsum()]
        ):
            writer.writerow([
                round(meter, 3), *np.round(point, 7), round(original, 2),
                round(filtered, 2), round(flat_kwh, 6), round(graded_kwh, 6),
            ])
    result = {
        "kind": kind, "origin": start_name, "destination": end_name,
        "distance_km": round(distance[-1] / 1000, 3),
        "speed_kmh": speed, "samples": len(distance),
        "start_snap_m": round(distance_m(start_coord, points[0]), 1),
        "end_snap_m": round(distance_m(end_coord, points[-1]), 1),
        "start_elevation_m": round(raw[0], 1), "end_elevation_m": round(raw[-1], 1),
        "ascent_m": round(np.maximum(dh, 0).sum(), 1),
        "descent_m": round(-np.minimum(dh, 0).sum(), 1),
        "max_abs_smoothed_grade_pct": round(100 * np.abs(dh / ds).max(), 1),
        "flat_kwh": round(flat.sum(), 4),
        "with_grade_kwh": round(graded.sum(), 4),
        "difference_kwh": round((graded - flat).sum(), 4),
        "difference_pct": round(100 * (graded - flat).sum() / flat.sum(), 1),
        "smoothing_sensitivity_kwh": {
            str(window): round(battery_energy(ds, np.diff(smooth_height(raw, ds[0], window)), speed).sum(), 4)
            for window in (90, 210)
        },
    }
    return result, (distance, raw, smoothed)


def save_figure(output, results, profiles):
    fig, axes = plt.subplots(2, 2, figsize=(11, 6.4), layout="constrained")
    fig.suptitle("How road grade changes EV battery use", fontsize=19, fontweight="bold")
    for index, (result_pair, profile_pair) in enumerate(zip(
        (results[:2], results[2:]), (profiles[:2], profiles[2:])
    )):
        uphill, downhill = result_pair
        profile_ax, energy_ax = axes[index]
        distance, raw, smoothed = profile_pair[0]
        profile_ax.plot(distance / 1000, raw, color="#a0b5c0", lw=1, label="Raw DEM")
        profile_ax.plot(distance / 1000, smoothed, color="#12596d", lw=2, label="Smoothed")
        profile_ax.set(title=f"{uphill['origin']} to {uphill['destination']}",
                       xlabel="Distance (km)", ylabel="Elevation (m)")
        profile_ax.legend(frameon=False, loc="upper left", fontsize=9)
        x = np.arange(2)
        for offset, key, color, label in [
            (-0.18, "flat_kwh", "#9eb9c7", "Flat road"),
            (0.18, "with_grade_kwh", "#006b64", "With grade"),
        ]:
            bars = energy_ax.bar(x + offset, [item[key] for item in result_pair], .36,
                                 color=color, label=label)
            energy_ax.bar_label(bars, fmt="%.2f", padding=3, fontsize=9)
        energy_ax.axhline(0, color="#4c5b60", lw=.7)
        energy_ax.margins(y=.18)
        energy_ax.set(xticks=x, xticklabels=[
            f"{uphill['origin']} → {uphill['destination']}",
            f"{downhill['origin']} → {downhill['destination']}",
        ], ylabel="Net battery use (kWh)")
        energy_ax.legend(frameon=False, fontsize=9)
        for ax in (profile_ax, energy_ax):
            ax.spines[["top", "right"]].set_visible(False)
            ax.set_axisbelow(True)
            ax.grid(axis="y", alpha=.20)
    fig.savefig(output / "comparison.png", dpi=160)
    plt.close(fig)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--build-graph", action="store_true")
    args = parser.parse_args()
    output = args.output.resolve()
    data = output / "data"
    dem_tiles = sorted(data.glob("Copernicus_DSM_COG_10_*.tif"))
    if not dem_tiles:
        parser.error(f"Put Copernicus GeoTIFF tiles in {data}")
    graph_dir = data / "valhalla_tiles"
    if args.build_graph:
        graph_dir.mkdir(exist_ok=True)
    elif not next(graph_dir.rglob("*.gph"), None):
        parser.error("Local Valhalla graph is missing. Run with --build-graph first.")
    config = get_config(tile_dir=str(graph_dir), tile_extract="", verbose=args.build_graph)
    config["mjolnir"]["concurrency"] = 4
    if args.build_graph:
        osm_file = data / "iran.osm.pbf"
        if not osm_file.is_file():
            parser.error(f"Put the OSM extract at {osm_file}")
        config_path = data / "valhalla.json"
        config_path.write_text(json.dumps(config, indent=2))
        subprocess.run([sys.executable, "-m", "valhalla", "valhalla_build_tiles",
                        "-c", str(config_path), str(osm_file)], check=True)
    actor = Actor(config)
    results, profiles = [], []
    for kind, (origin, destination, speed) in ROUTES.items():
        for start, finish in ((origin, destination), (destination, origin)):
            result, profile = evaluate_route(actor, output, dem_tiles, kind, start, finish, speed)
            results.append(result)
            profiles.append(profile)
    report = {
        "vehicle": asdict(VEHICLE), "sample_spacing_target_m": SAMPLE_M,
        "smoothing_window_target_m": SMOOTH_M, "dem_files": [path.name for path in dem_tiles],
        "results": results,
    }
    rendered = json.dumps(report, indent=2)
    (output / "results.json").write_text(rendered + "\n")
    save_figure(output, results, profiles)
    print(rendered)


if __name__ == "__main__":
    main()
