import re

from app.domain.text import normalize_fa

_SOURCE_NAMES = ("sharinet", "ocm", "abrp")
_SOURCE_TOKENS = {*_SOURCE_NAMES, "شارینت"}
_SLUG_MAX = 120


def public_location_slug(value: str) -> str:
    """Public station URL segment. Source names never appear in it."""
    slug = re.sub(r"[^a-z0-9]+", "-", (value or "").lower()).strip("-")
    while slug:
        removed = False
        for name in _SOURCE_NAMES:
            if slug == name:
                slug = ""
                removed = True
                break
            prefix = f"{name}-"
            if slug.startswith(prefix):
                slug = slug[len(prefix) :]
                removed = True
                break
        if not removed:
            break
    return (slug or "location")[:70]


def slugify_fa(value: str) -> str:
    text = normalize_fa(value)
    text = re.sub(r"[^\u0600-\u06ffa-z0-9]+", "-", text)
    return re.sub(r"-{2,}", "-", text).strip("-")


def station_slug(name: str, province: str | None) -> str:
    """Public URL segment: province first, then the station name. No data-source name."""
    parts = [part for part in slugify_fa(normalize_fa(name, cluster_key=True)).split("-") if part not in _SOURCE_TOKENS]
    place = "-".join(parts)
    prov = slugify_fa(province or "")
    if prov and place and place != prov and not place.startswith(f"{prov}-"):
        slug = f"{prov}-{place}"
    else:
        slug = place or prov or "ایستگاه"
    return slug[:_SLUG_MAX].strip("-")
