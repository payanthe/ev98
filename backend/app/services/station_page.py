import json
import re
from html import escape
from pathlib import Path

from app.schemas.api import LocationDetail


def station_summary(location: LocationDetail) -> str:
    place = "، ".join(part for part in (location.city, location.province) if part)
    plugs = list(
        dict.fromkeys(
            connector.standard_label
            for evse in location.evses
            for connector in evse.connectors
            if connector.standard_label
        )
    )
    name = re.sub(r"^ایستگاه\s+شارژ\s+", "", location.name)
    operator = (location.operator_name or "").strip()
    if operator.casefold() in {"unknown", "unknown operator", "نامشخص"} or "unknown" in operator.casefold():
        operator = ""
    parts = [
        f"ایستگاه شارژ {name}",
        f"در {place}" if place else None,
        f"اپراتور {operator}" if operator else None,
        f"حداکثر توان {location.max_power_kw:g} کیلووات" if location.max_power_kw is not None else None,
        f"کانکتور {'، '.join(plugs)}" if plugs else None,
        location.hours_label or location.hours_summary,
    ]
    return f"{'، '.join(part for part in parts if part)}."


def _replace(html: str, pattern: str, replacement: str) -> str:
    return re.sub(pattern, lambda _match: replacement, html, count=1, flags=re.IGNORECASE | re.DOTALL)


def render_station_page(index_path: str, origin: str, location: LocationDetail | None, slug: str) -> str:
    html = Path(index_path).read_text(encoding="utf-8")
    if location is None:
        html = _replace(html, r"<title>.*?</title>", "<title>ایستگاه پیدا نشد | EV98</title>")
        html = _replace(html, r'<meta\s+name="robots"[^>]*>', '<meta name="robots" content="noindex, follow">')
        return html

    base = origin.rstrip("/")
    url = f"{base}/stations/{escape(location.slug or slug, quote=True)}"
    title = f"{location.name}{f' در {location.city}' if location.city else ''} | EV98"
    summary = station_summary(location)
    image = location.images[0] if location.images else f"{base}/og-image.png"
    replacements = {
        r"<title>.*?</title>": f"<title>{escape(title)}</title>",
        r'<meta\s+name="description"[^>]*>': f'<meta name="description" content="{escape(summary, quote=True)}">',
        r'<meta\s+name="robots"[^>]*>': '<meta name="robots" content="index, follow, max-image-preview:large">',
        r'<link\s+rel="canonical"[^>]*>': f'<link rel="canonical" href="{url}">',
        r'<meta\s+property="og:title"[^>]*>': f'<meta property="og:title" content="{escape(title, quote=True)}">',
        r'<meta\s+property="og:description"[^>]*>': f'<meta property="og:description" content="{escape(summary, quote=True)}">',
        r'<meta\s+property="og:url"[^>]*>': f'<meta property="og:url" content="{url}">',
        r'<meta\s+property="og:image"[^>]*>': f'<meta property="og:image" content="{escape(image, quote=True)}">',
        r'<meta\s+name="twitter:title"[^>]*>': f'<meta name="twitter:title" content="{escape(title, quote=True)}">',
        r'<meta\s+name="twitter:description"[^>]*>': f'<meta name="twitter:description" content="{escape(summary, quote=True)}">',
        r'<meta\s+name="twitter:image"[^>]*>': f'<meta name="twitter:image" content="{escape(image, quote=True)}">',
    }
    for pattern, replacement in replacements.items():
        html = _replace(html, pattern, replacement)

    schema = {
        "@context": "https://schema.org",
        "@graph": [
            {
                "@type": "WebPage",
                "@id": f"{url}#page",
                "url": url,
                "name": title,
                "description": summary,
                "inLanguage": "fa-IR",
                "mainEntity": {"@id": f"{url}#place"},
            },
            {
                "@type": "Place",
                "@id": f"{url}#place",
                "name": location.name,
                "description": summary,
                "url": url,
                "telephone": location.phone,
                "image": location.images or None,
                "address": {
                    "@type": "PostalAddress",
                    "streetAddress": location.address,
                    "addressLocality": location.city,
                    "addressRegion": location.province,
                    "addressCountry": "IR",
                },
                "geo": {
                    "@type": "GeoCoordinates",
                    "latitude": location.lat,
                    "longitude": location.lng,
                },
            },
        ],
    }
    payload = json.dumps(schema, ensure_ascii=False, separators=(",", ":")).replace("</", "<\\/")
    html = html.replace("</head>", f'<script id="station-jsonld" type="application/ld+json">{payload}</script>\n  </head>', 1)
    return html
