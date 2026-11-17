"""Local place search and approximate reverse lookup for the trip planner."""
from contextlib import closing, contextmanager
import math
import sqlite3

from app.api.errors import AppError
from app.core.config import settings

from app.services.place_names import place_tokens


@contextmanager
def _index():
    try:
        uri = f"{settings.offline_trip_dir.resolve().as_uri()}/places.sqlite?mode=ro"
        with closing(sqlite3.connect(uri, uri=True)) as db:
            db.row_factory = sqlite3.Row
            yield db
    except sqlite3.Error as exc:
        raise AppError(503, "Place index unavailable", "دادهٔ محلی جست‌وجوی مکان در دسترس نیست.") from exc


def search_places(query: str) -> list[dict]:
    tokens = place_tokens(query)
    if not tokens:
        return []
    road_terms = {"خیابان", "بلوار", "کوچه", "بزرگراه"}
    shorter = [token for token in tokens if token not in road_terms]
    groups = [tokens, shorter] if shorter and shorter != tokens else [tokens]
    expressions = []
    for group in groups:
        terms = [f'"{token}"' for token in group]
        terms[-1] += "*"
        expressions.append("(" + " AND ".join(terms) + ")")
    match = " OR ".join(expressions)
    compact = "".join(tokens)
    shorter_compact = "".join(shorter)
    with _index() as db:
        rows = db.execute(
            """WITH hits AS (
                   SELECT rowid AS id, rank AS relevance FROM names WHERE names MATCH ?
                   UNION ALL
                   SELECT id, -1.0 FROM places WHERE replace(normalized, ' ', '') = ?
               )
               SELECT p.title, p.locality, p.lat, p.lng
               FROM hits JOIN places p USING (id)
               GROUP BY p.id
               ORDER BY CASE
                   WHEN replace(p.normalized, ' ', '') = ? THEN 0
                   WHEN ? IN (replace(p.normalized || p.locality, ' ', ''),
                              replace(p.locality || p.normalized, ' ', '')) THEN 1
                   WHEN ? IN (replace(p.normalized || p.locality, ' ', ''),
                              replace(p.locality || p.normalized, ' ', '')) THEN 2
                   ELSE 3 END,
                   CASE WHEN ? AND p.priority = 3 THEN 0 ELSE 1 END,
                   p.priority, min(hits.relevance), p.title, p.id
               LIMIT 5""",
            (match, compact, compact, compact, shorter_compact, len(groups) > 1),
        ).fetchall()
    return [
        {"title": row["title"], "address": row["locality"], "lat": row["lat"], "lng": row["lng"]}
        for row in rows
    ]


def reverse_place(point) -> dict:
    lng_scale = math.cos(math.radians(point.lat))
    with _index() as db:
        row = db.execute(
            """SELECT p.title, p.locality
               FROM nearby n JOIN places p ON p.id = n.id
               WHERE n.min_lat <= ? AND n.max_lat >= ? AND n.min_lng <= ? AND n.max_lng >= ?
               ORDER BY ((p.lat - ?) * (p.lat - ?)) +
                        ((p.lng - ?) * (p.lng - ?) * ?)
               LIMIT 1""",
            (point.lat + .006, point.lat - .006, point.lng + .008, point.lng - .008,
             point.lat, point.lat, point.lng, point.lng, lng_scale**2),
        ).fetchone()
    address = "موقعیت انتخاب‌شده روی نقشه"
    if row:
        address = f"نزدیک {row['title']}"
        if row["locality"]:
            address += f"، {row['locality']}"
    return {"title": address, "address": address, "lat": point.lat, "lng": point.lng}
