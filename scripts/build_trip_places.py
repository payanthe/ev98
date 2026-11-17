# /// script
# requires-python = ">=3.12"
# dependencies = ["osmium"]
# ///
"""Build the trip planner's searchable place index from a local OpenStreetMap PBF."""
import argparse
from collections import defaultdict
from functools import lru_cache
from itertools import chain
import math
from pathlib import Path
import sqlite3
import sys
from tempfile import TemporaryDirectory

import osmium

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))
from app.services.place_names import place_tokens

SETTLEMENTS = {"city", "town", "village", "hamlet", "suburb", "neighbourhood", "quarter", "locality", "square"}
ROAD_CLASSES = {"motorway", "trunk", "primary", "secondary", "tertiary", "unclassified", "residential", "living_street", "pedestrian", "service"}
CELL = .25


def key(point):
    lat, lng = point
    return math.floor(lat / CELL), math.floor(lng / CELL)


class Settlements(osmium.SimpleHandler):
    def __init__(self):
        super().__init__()
        self.cells = defaultdict(list)

    def node(self, node):
        label = node.tags.get("name:fa") or node.tags.get("name")
        level = node.tags.get("place")
        if label and level in {"city", "town"} and node.location.valid():
            lat, lng = node.location.lat, node.location.lon
            self.cells[key((lat, lng))].append((lat, lng, label, level))

    @lru_cache(maxsize=200_000)
    def nearest(self, lat, lng):
        y, x = key((lat, lng))
        longitude_scale = math.cos(math.radians(lat)) ** 2
        candidates = chain.from_iterable(
            self.cells.get((y + dy, x + dx), ()) for dy in (-1, 0, 1) for dx in (-1, 0, 1)
        )
        best = min(candidates, key=lambda p: ((p[0] - lat)**2 + (p[1] - lng)**2 * longitude_scale) * (.60 if p[3] == "city" else 1), default=None)
        return best[2] if best else ""


class Features(osmium.SimpleHandler):
    def __init__(self, db, settlements):
        super().__init__()
        self.db = db
        self.settlements = settlements
        self.rows = []

    def add(self, tags, lat, lng):
        title = tags.get("name:fa") or tags.get("name")
        if not title:
            return
        place, road = tags.get("place"), tags.get("highway")
        if place in {"city", "town", "village"}:
            priority = 0 if place == "city" else 1
        elif place in SETTLEMENTS or tags.get("junction") == "roundabout" or tags.get("leisure") == "park":
            priority = 2
        elif road in ROAD_CLASSES:
            priority = 3
        elif any(tags.get(tag) for tag in ("amenity", "tourism", "railway", "shop", "historic", "public_transport")):
            priority = 4
        else:
            return
        normalized = " ".join(place_tokens(title))
        if not normalized:
            return
        locality = tags.get("addr:city") or ""
        if len(locality) > 35 or any(mark in locality for mark in "،,/؛"):
            locality = ""
        if not locality and place not in {"city", "town", "village"}:
            locality = self.settlements.nearest(round(lat, 2), round(lng, 2))
        if locality == title:
            locality = ""
        aliases = " ".join(place_tokens(" ".join(filter(None, (
            tags.get("name"), tags.get("name:en"), tags.get("alt_name"),
            tags.get("short_name"), tags.get("old_name"), locality,
        )))))
        if " " in normalized:
            aliases = f"{aliases} {normalized.replace(' ', '')}".strip()
        # Keep homonyms in separate areas while grouping split ways in the same area.
        self.rows.append((title, normalized, aliases, locality, lat, lng, priority, round(lat, 2), round(lng, 2)))
        if len(self.rows) >= 5000:
            self.flush()

    def node(self, node):
        if node.location.valid():
            self.add(node.tags, node.location.lat, node.location.lon)

    def way(self, way):
        if not (way.tags.get("name") or way.tags.get("name:fa")) or not len(way.nodes):
            return
        location = way.nodes[len(way.nodes) // 2].location
        if location.valid():
            self.add(way.tags, location.lat, location.lon)

    def flush(self):
        self.db.executemany(
            """INSERT INTO places(title,normalized,aliases,locality,lat,lng,priority,cell_lat,cell_lng)
               VALUES(?,?,?,?,?,?,?,?,?)
               ON CONFLICT(normalized,cell_lat,cell_lng) DO UPDATE SET
                   title=excluded.title, aliases=excluded.aliases, locality=excluded.locality,
                   lat=excluded.lat, lng=excluded.lng, priority=excluded.priority
               WHERE excluded.priority < places.priority""",
            self.rows,
        )
        self.rows.clear()


def build(pbf, output):
    settlements = Settlements()
    settlements.apply_file(str(pbf))
    output.parent.mkdir(parents=True, exist_ok=True)
    with TemporaryDirectory(dir=output.parent) as temporary:
        candidate = Path(temporary) / output.name
        db = sqlite3.connect(candidate)
        try:
            db.executescript("""
                CREATE TABLE places (
                    id INTEGER PRIMARY KEY, title TEXT, normalized TEXT, aliases TEXT, locality TEXT,
                    lat REAL, lng REAL, priority INTEGER, cell_lat REAL, cell_lng REAL,
                    UNIQUE(normalized, cell_lat, cell_lng)
                );
                CREATE VIRTUAL TABLE names USING fts5(normalized, aliases, content=places, content_rowid=id, prefix='2 3');
                CREATE VIRTUAL TABLE nearby USING rtree(id, min_lat, max_lat, min_lng, max_lng);
            """)
            features = Features(db, settlements)
            features.apply_file(str(pbf), locations=True, idx="flex_mem")
            features.flush()
            db.execute("CREATE INDEX compact_place_name ON places(replace(normalized, ' ', ''))")
            db.execute("INSERT INTO names(names) VALUES('rebuild')")
            db.execute("INSERT INTO nearby SELECT id, lat, lat, lng, lng FROM places")
            db.commit()
            print(f"{db.execute('SELECT COUNT(*) FROM places').fetchone()[0]:,} features indexed")
        finally:
            db.close()
        candidate.replace(output)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("pbf", type=Path)
    parser.add_argument("output", type=Path)
    options = parser.parse_args()
    build(options.pbf, options.output)
