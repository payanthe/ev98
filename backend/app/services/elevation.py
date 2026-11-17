"""Shared elevation sampling and battery model for the EV98 pilot and planner."""
from dataclasses import dataclass
from math import asin, cos, radians, sin, sqrt

import numpy as np
import rasterio
from rasterio.transform import rowcol
from rasterio.windows import Window

SAMPLE_M = 30
SMOOTH_M = 150


class ElevationUnavailable(ValueError):
    pass


@dataclass(frozen=True)
class Vehicle:
    mass_kg: float = 1850
    drag_area_m2: float = 0.65
    rolling_coefficient: float = 0.012
    drive_efficiency: float = 0.90
    regen_efficiency: float = 0.65
    regen_limit_w: float = 40_000
    auxiliary_w: float = 800


VEHICLE = Vehicle()


def distance_m(a, b):
    lon_a, lat_a = map(radians, a)
    lon_b, lat_b = map(radians, b)
    haversine = sin((lat_b - lat_a) / 2)**2
    haversine += cos(lat_a) * cos(lat_b) * sin((lon_b - lon_a) / 2)**2
    return 12_742_000 * asin(sqrt(min(1, haversine)))


def resample(shape):
    lengths = np.array([distance_m(a, b) for a, b in zip(shape[:-1], shape[1:])])
    if not np.any(lengths > 0):
        return np.array([]), np.empty((0, 2))
    keep = np.r_[True, lengths > 0]
    path_m = np.r_[0, lengths.cumsum()][keep]
    # Nearly uniform spacing with both exact route endpoints included.
    sample_m = np.linspace(0, path_m[-1], int(np.ceil(path_m[-1] / SAMPLE_M)) + 1)
    samples = np.column_stack([
        np.interp(sample_m, path_m, column[keep]) for column in shape.T
    ])
    return sample_m, samples


def read_elevations(dem_tiles, points, *, require_complete=True):
    heights = np.full(len(points), np.nan)
    # Nearest pixel sampling on the native grid, including at the tile seam.
    for filename in dem_tiles:
        with rasterio.open(filename) as tile:
            if tile.crs is None or tile.crs.to_epsg() != 4326:
                raise ElevationUnavailable(f"Expected an EPSG:4326 DEM: {filename}")
            bounds = tile.bounds
            lon, lat = points.T
            use = np.flatnonzero((bounds.left <= lon) & (lon < bounds.right)
                                 & (bounds.bottom < lat) & (lat <= bounds.top))
            if not len(use):
                continue
            rows, cols = rowcol(tile.transform, lon[use], lat[use])
            inside = (0 <= rows) & (rows < tile.height) & (0 <= cols) & (cols < tile.width)
            use, rows, cols = use[inside], rows[inside], cols[inside]
            block_height, block_width = tile.block_shapes[0]
            block_rows, block_cols = rows // block_height, cols // block_width
            # Read a touched TIFF block once rather than requesting a pixel per sample.
            for br, bc in np.unique(np.column_stack((block_rows, block_cols)), axis=0):
                take = (block_rows == br) & (block_cols == bc)
                r, c = int(br) * block_height, int(bc) * block_width
                window = Window(c, r, min(block_width, tile.width - c), min(block_height, tile.height - r))
                pixels = tile.read(1, window=window, masked=True)
                sampled = pixels[rows[take] - r, cols[take] - c]
                finite = ~np.ma.getmaskarray(sampled) & np.isfinite(sampled.data)
                heights[use[take][finite]] = sampled.data[finite]
    if require_complete and not np.all(np.isfinite(heights)):
        missing = points[~np.isfinite(heights)]
        raise ElevationUnavailable(f"DEM missing {len(missing)} sample(s); first at {missing[0]}")
    return heights


def smooth_height(heights, sample_spacing, window_m):
    half_width = min(len(heights) - 1, max(1, int(window_m / (2 * sample_spacing))))
    # Preserve the endpoints by reflecting the local elevation trend.
    padded = np.pad(heights, half_width, mode="reflect", reflect_type="odd")
    return np.convolve(padded, np.full(2 * half_width + 1, 1 / (2 * half_width + 1)), mode="valid")


def battery_energy(ds, dh, speed_kmh):
    """Return net battery kWh, per segment, for steady-speed driving."""
    return battery_flow(ds, dh, speed_kmh)[0]


def battery_flow(ds, dh, speed_kmh):
    """Return net battery kWh and recoverable braking kWh per segment."""
    speed = speed_kmh / 3.6
    vehicle = VEHICLE
    gravity_n = vehicle.mass_kg * 9.80665
    rolling_j = vehicle.rolling_coefficient * gravity_n * ds
    drag_j = 0.5 * 1.20 * vehicle.drag_area_m2 * speed**2 * np.hypot(ds, dh)
    wheel_j = rolling_j + drag_j + gravity_n * dh
    seconds = np.hypot(ds, dh) / speed
    battery_j = np.where(
        wheel_j >= 0,
        wheel_j / vehicle.drive_efficiency,
        np.maximum(wheel_j * vehicle.regen_efficiency, -vehicle.regen_limit_w * seconds),
    ) + vehicle.auxiliary_w * seconds
    recoverable_j = np.minimum(np.maximum(-wheel_j, 0) * vehicle.regen_efficiency,
                               vehicle.regen_limit_w * seconds)
    return battery_j / 3_600_000, recoverable_j / 3_600_000
