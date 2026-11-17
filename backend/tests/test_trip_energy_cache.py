import os

import numpy as np
import pytest
import rasterio
from rasterio.transform import from_origin

from app.services import trip_energy
from app.services.elevation import distance_m
from app.services.trip_energy import TripEnergy
from app.services.trip_router import Point, RoadLeg


def _write_tile(path, height):
    with rasterio.open(
        path, "w", driver="GTiff", width=64, height=64, count=1, dtype="int16",
        crs="EPSG:4326", transform=from_origin(51.38, 35.72, 0.001, 0.001),
    ) as tile:
        tile.write(np.full((64, 64), height, dtype=np.int16), 1)


@pytest.fixture
def terrain_route(tmp_path, monkeypatch):
    tile = tmp_path / "Copernicus_DSM_COG_30_test.tif"
    _write_tile(tile, 100)
    shape = (Point(35.7, 51.4), Point(35.7, 51.41))
    distance = distance_m(*[(p.lng, p.lat) for p in shape])
    monkeypatch.setattr(trip_energy, "structure_spans", lambda *_: [])
    return tile, RoadLeg(distance, 60, shape)


def test_profile_cache_checks_current_terrain_and_preserves_battery_inputs(terrain_route, monkeypatch):
    tile, leg = terrain_route
    first = TripEnergy(300_000, 60, tile.parent).for_leg(leg)
    repeat = TripEnergy(300_000, 60, tile.parent).for_leg(leg)
    assert repeat is first
    assert not repeat.terrain.heights.flags.writeable
    assert np.allclose(first.terrain.heights, 100)

    other_vehicle = TripEnergy(150_000, 60, tile.parent).for_leg(leg)
    assert other_vehicle.net_soc == pytest.approx(first.net_soc * 2)

    # An atomic replacement still invalidates the cache if the file retains its mtime.
    replacement = tile.with_suffix(".new")
    _write_tile(replacement, 200)
    original = tile.stat()
    os.utime(replacement, ns=(original.st_atime_ns, original.st_mtime_ns))
    replacement.replace(tile)
    updated = TripEnergy(300_000, 60, tile.parent).for_leg(leg)
    assert np.allclose(updated.terrain.heights, 200)

    monkeypatch.setattr(trip_energy, "structure_spans", lambda *_: None)
    assert not TripEnergy(300_000, 60, tile.parent).for_leg(leg).terrain.structures_checked


def test_profile_cache_retries_failed_lateral_samples(terrain_route, monkeypatch):
    tile, leg = terrain_route
    real_sample = trip_energy.uncertain_samples

    def failed_sample(*_):
        raise OSError("Transient DEM read error")

    monkeypatch.setattr(trip_energy, "uncertain_samples", failed_sample)
    degraded = TripEnergy(300_000, 60, tile.parent).for_leg(leg)
    monkeypatch.setattr(trip_energy, "uncertain_samples", real_sample)
    recovered = TripEnergy(300_000, 60, tile.parent).for_leg(leg)
    assert recovered is not degraded
    assert recovered is TripEnergy(300_000, 60, tile.parent).for_leg(leg)
