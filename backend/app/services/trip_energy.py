"""Apply the elevation model as a correction to the catalog-based flat range."""
from collections import OrderedDict
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from threading import Lock

import numpy as np
import rasterio
from rasterio.errors import RasterioError

from app.services.elevation import ElevationUnavailable, battery_energy, battery_flow, read_elevations, resample
from app.services.road_terrain import TerrainSpan, prepare_terrain, structure_spans, uncertain_samples
from app.services.trip_router import Point, RoadLeg


@dataclass(frozen=True)
class TerrainTrace:
    meters: np.ndarray
    heights: np.ndarray
    uphill_m: np.ndarray
    downhill_m: np.ndarray
    draw_kwh: np.ndarray
    regen_kwh: np.ndarray
    resolution_m: int
    quality: tuple[TerrainSpan, ...] = ()
    structures_checked: bool = True


@dataclass(frozen=True)
class LegEnergy:
    net_soc: float
    peak_draw_soc: float
    min_prefix_soc: float = 0
    max_draw_after_regen_soc: float = 0
    uses_grade: bool = False
    terrain: TerrainTrace | None = None

    def reaches(self, start_soc: float, reserve_soc: float) -> bool:
        # Check both the drop from departure and the drop after any full-charge cap.
        return (start_soc - self.peak_draw_soc >= reserve_soc - 1e-9
                and 100 - self.max_draw_after_regen_soc >= reserve_soc - 1e-9)

    def arrival(self, start_soc: float) -> float:
        overflow = max(0., start_soc - 100 - self.min_prefix_soc)
        return min(100., start_soc - self.net_soc - overflow)


@lru_cache(maxsize=512)
def _bounds(path: Path, revision: tuple[int, ...]):
    with rasterio.open(path) as tile:
        return tile.bounds


# Allow several long legs without retaining their Python point objects.
_MAX_CACHED_PROFILES = 64
_MAX_PROFILE_CACHE_BYTES = 32 * 1024 * 1024
_profile_cache = OrderedDict()
_profile_cache_lock = Lock()
_profile_cache_bytes = 0


def _save_profile(key: tuple, profile: LegEnergy, size: int) -> None:
    global _profile_cache_bytes
    if size > _MAX_PROFILE_CACHE_BYTES:
        return
    with _profile_cache_lock:
        if key in _profile_cache:
            _profile_cache.move_to_end(key)
            return
        while (len(_profile_cache) >= _MAX_CACHED_PROFILES
               or _profile_cache_bytes + size > _MAX_PROFILE_CACHE_BYTES):
            _, (_, removed_size) = _profile_cache.popitem(last=False)
            _profile_cache_bytes -= removed_size
        _profile_cache[key] = (profile, size)
        _profile_cache_bytes += size


class TripEnergy:
    def __init__(self, range_m: float, battery_kwh: float | None, elevation_dir: Path | None):
        self.range_m = range_m
        self.battery_kwh = battery_kwh if battery_kwh and battery_kwh > 0 else None
        self.tiles = {30: {}, 90: {}}
        revisions = []
        complete_inventory = True
        if elevation_dir is not None and self.battery_kwh is not None:
            for resolution, code in ((30, "10"), (90, "30")):
                for path in sorted(elevation_dir.glob(f"Copernicus_DSM_COG_{code}_*.tif")):
                    try:
                        info = path.stat()
                        revision = (info.st_dev, info.st_ino, info.st_size, info.st_mtime_ns, info.st_ctime_ns)
                        self.tiles[resolution][path] = _bounds(path, revision)
                        revisions.append((path, revision))
                    except (OSError, RasterioError):
                        complete_inventory = False
                        continue
        self._tile_revision = tuple(revisions) if complete_inventory else None

    def covers(self, point: Point) -> bool:
        return any(b.left <= point.lng < b.right and b.bottom < point.lat <= b.top
                   for tiles in self.tiles.values() for b in tiles.values())

    def flat(self, distance_m: float) -> LegEnergy:
        draw = distance_m / self.range_m * 100
        return LegEnergy(draw, draw, max_draw_after_regen_soc=draw)

    def for_leg(self, leg: RoadLeg) -> LegEnergy:
        if (len(leg.shape) < 2 or leg.duration_s <= 0 or not self.covers(leg.shape[0])
                or not self.covers(leg.shape[-1])):
            return self.flat(leg.distance_m)
        shape = np.array([(point.lng, point.lat) for point in leg.shape])
        meters, samples = resample(shape)
        if len(meters) < 2 or abs(meters[-1] - leg.distance_m) > max(15, leg.distance_m * .02):
            return self.flat(leg.distance_m)
        # Recheck structures on the current graph, including recovery from an unavailable trace.
        structures = structure_spans(leg, meters[-1])
        cache_key = None
        if self._tile_revision is not None:
            shape_key = shape.tobytes()
            cache_key = (shape_key, leg.distance_m, leg.duration_s,
                         self.range_m, self.battery_kwh, self._tile_revision,
                         None if structures is None else tuple(structures))
            with _profile_cache_lock:
                cached = _profile_cache.get(cache_key)
                if cached is not None:
                    _profile_cache.move_to_end(cache_key)
                    return cached[0]

        lon, lat = samples.T
        west, east, south, north = lon.min(), lon.max(), lat.min(), lat.max()
        for resolution, available in self.tiles.items():
            tiles = [path for path, bounds in available.items()
                     if bounds.left <= east + .001 and bounds.right > west - .001
                     and bounds.bottom < north + .001 and bounds.top >= south - .001]
            try:
                heights = read_elevations(tiles, samples)
            except ElevationUnavailable:
                continue
            except (RasterioError, OSError):
                cache_key = None
                continue
            break
        else:
            return self.flat(leg.distance_m)
        try:
            uncertain = uncertain_samples(tiles, samples, heights)
        except (ElevationUnavailable, OSError, RasterioError):
            cache_key = None
            uncertain = np.zeros(len(samples), dtype=bool)
        try:
            meters, heights, quality = prepare_terrain(meters, heights, uncertain, structures or [], resolution)
        except ElevationUnavailable:
            return self.flat(leg.distance_m)
        ds = np.diff(meters)
        dh = np.diff(heights)
        speed_kmh = leg.distance_m / leg.duration_s * 3.6
        graded, regen = battery_flow(ds, dh, speed_kmh)
        flat = battery_energy(ds, np.zeros_like(ds), speed_kmh)
        catalog_kwh = leg.distance_m / self.range_m * self.battery_kwh
        draw = np.maximum(0, ds / meters[-1] * catalog_kwh + (graded + regen - flat))
        segment_soc = (draw - regen) / self.battery_kwh * 100
        prefixes = np.r_[0., segment_soc.cumsum()]
        scale = leg.distance_m / meters[-1]
        road_m = meters * scale
        road_ds = np.diff(road_m)
        road_quality = tuple(TerrainSpan(q.start_m * scale, q.end_m * scale, q.kind) for q in quality)
        terrain = TerrainTrace(
            road_m, heights, np.where(dh / ds >= .01, road_ds, 0),
            np.where(dh / ds <= -.01, road_ds, 0), draw, regen, resolution,
            road_quality, structures is not None,
        )
        profile = LegEnergy(
            net_soc=float(prefixes[-1]), peak_draw_soc=float(prefixes.max()),
            min_prefix_soc=float(prefixes.min()),
            max_draw_after_regen_soc=float((prefixes - np.minimum.accumulate(prefixes)).max()),
            uses_grade=True, terrain=terrain,
        )
        if cache_key is not None:
            arrays = (terrain.meters, terrain.heights, terrain.uphill_m,
                      terrain.downhill_m, terrain.draw_kwh, terrain.regen_kwh)
            for values in arrays:
                values.setflags(write=False)
            # Estimate the Python metadata overhead in addition to the measured array sizes.
            metadata_bytes = 256 * (len(terrain.quality) + len(structures or ()) + len(self._tile_revision))
            _save_profile(cache_key, profile, len(shape_key) + sum(a.nbytes for a in arrays) + metadata_bytes)
        return profile

    def kwh(self, soc: float) -> float | None:
        return round(soc * self.battery_kwh / 100, 3) if self.battery_kwh is not None else None
