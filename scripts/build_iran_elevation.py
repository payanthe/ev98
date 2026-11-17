# /// script
# requires-python = ">=3.12"
# dependencies = ["osmium", "rasterio"]
# ///
"""Install public Copernicus GLO-90 tiles needed by the local OSM road graph."""
import argparse
from concurrent.futures import ThreadPoolExecutor, as_completed
import json
import math
from pathlib import Path
import subprocess
from tempfile import TemporaryDirectory

import osmium
import rasterio
from rasterio.errors import RasterioError

ROAD_TYPES = {
    "motorway", "trunk", "primary", "secondary", "tertiary", "unclassified",
    "residential", "living_street", "service", "track", "road", "motorway_link",
    "trunk_link", "primary_link", "secondary_link", "tertiary_link",
}
# Include cells touching a way within a few raster pixels of a tile boundary.
BUFFER = .002


class RoadCells(osmium.SimpleHandler):
    def __init__(self):
        super().__init__()
        self.cells = set()

    def way(self, way):
        if way.tags.get("highway") not in ROAD_TYPES:
            return
        previous = None
        for node in way.nodes:
            if not node.location.valid():
                previous = None
                continue
            current = (node.lat, node.lon)
            if previous is not None:
                # Minute cell count per way, including paths that cross a corner.
                south, north = sorted((previous[0], current[0]))
                west, east = sorted((previous[1], current[1]))
                for lat in range(math.floor(south - BUFFER), math.floor(north + BUFFER) + 1):
                    for lon in range(math.floor(west - BUFFER), math.floor(east + BUFFER) + 1):
                        self.cells.add((lat, lon))
            previous = current


def validate(path):
    try:
        with rasterio.open(path) as raster:
            return raster.crs.to_epsg() == 4326 and raster.shape == (1200, 1200) and raster.count == 1
    except (AttributeError, RasterioError, OSError):
        return False


def fetch(cell, output):
    lat, lon = cell
    prefix = f"Copernicus_DSM_COG_30_{'N' if lat >= 0 else 'S'}{abs(lat):02d}_00_{'E' if lon >= 0 else 'W'}{abs(lon):03d}_00_DEM"
    target = output / f"{prefix}.tif"
    if target.is_file() and validate(target):
        return target
    url = f"https://copernicus-dem-90m.s3.amazonaws.com/{prefix}/{prefix}.tif"
    with TemporaryDirectory(dir=output) as directory:
        part = Path(directory) / target.name
        result = subprocess.run([
            "curl", "--silent", "--show-error", "--fail", "--retry", "3", "--retry-delay", "2",
            "--connect-timeout", "12", "--max-time", "180",
            "-w", "%{http_code}", "-o", str(part), url,
        ], text=True, capture_output=True)
        if result.stdout.strip().endswith("404"):
            return None
        if result.returncode or not validate(part):
            raise RuntimeError(f"{target.name}: {result.stderr.strip() or 'invalid raster'}")
        part.replace(target)
    return target


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("pbf", type=Path)
    parser.add_argument("output", type=Path)
    parser.add_argument("--workers", type=int, default=12)
    args = parser.parse_args()
    args.output.mkdir(exist_ok=True, parents=True)
    roads = RoadCells()
    roads.apply_file(str(args.pbf), locations=True, idx="flex_mem")
    cells = sorted(roads.cells, key=lambda p: (abs(p[0] - 34) + abs(p[1] - 51), p))
    print(f"{len(cells)} road cells in {args.pbf.name}", flush=True)
    files, missing, errors = [], [], []
    with ThreadPoolExecutor(max_workers=args.workers) as pool:
        work = {pool.submit(fetch, cell, args.output): cell for cell in cells}
        for i, future in enumerate(as_completed(work), 1):
            try:
                tile = future.result()
                if tile is None:
                    missing.append(work[future])
                else:
                    files.append(tile.name)
            except RuntimeError as exc:
                errors.append(str(exc))
            if i % 10 == 0 or i == len(cells):
                print(f"{i}/{len(cells)} checked, {len(files)} available, {len(missing)} absent", flush=True)
    if errors:
        raise SystemExit("\n".join(errors))
    manifest = {"source": "Copernicus GLO-90 on AWS", "osm_extract": args.pbf.name,
                "files": sorted(files), "source_does_not_have_tile": sorted(missing)}
    (args.output / "iran-glo90.json").write_text(json.dumps(manifest, indent=2) + "\n")


if __name__ == "__main__":
    main()
