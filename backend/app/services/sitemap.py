from datetime import datetime
from html import escape

from app.services.cars_page import CARS_PATH, CARS_UPDATED


def render_sitemap(origin: str, entries: list[tuple[str, datetime | None]]) -> str:
    base = origin.rstrip("/")
    lines = [
        '<?xml version="1.0" encoding="UTF-8"?>',
        '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">',
        f"<url><loc>{escape(base + '/', quote=True)}</loc></url>",
        f"<url><loc>{escape(base + CARS_PATH, quote=True)}</loc><lastmod>{CARS_UPDATED.isoformat()}</lastmod></url>",
    ]
    for slug, updated in entries:
        loc = escape(f"{base}/stations/{slug}", quote=True)
        lastmod = f"<lastmod>{updated.date().isoformat()}</lastmod>" if updated is not None else ""
        lines.append(f"<url><loc>{loc}</loc>{lastmod}</url>")
    lines.append("</urlset>")
    return "\n".join(lines) + "\n"
