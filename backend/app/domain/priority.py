from datetime import UTC, datetime

FIELD_PRIORITY: dict[str, dict[str, int]] = {
    "canonical_name_fa": {"ocm": 75, "sharinet": 70, "abrp": 50},
    "coordinates": {"sharinet": 85, "ocm": 70, "abrp": 60},
    "address": {"sharinet": 80, "ocm": 75, "abrp": 45},
    "phone": {"ocm": 80, "sharinet": 60, "abrp": 40},
    "website": {"ocm": 80, "sharinet": 50, "abrp": 40},
    "operator": {"sharinet": 90, "ocm": 70, "abrp": 65},
    "is_public": {"ocm": 80, "sharinet": 75, "abrp": 60},
    "is_24_7": {"sharinet": 70, "ocm": 65, "abrp": 40},
    "hours_summary": {"sharinet": 80, "ocm": 50, "abrp": 40},
    "facilities": {"sharinet": 80, "abrp": 55, "ocm": 40},
    "images": {"sharinet": 80, "ocm": 70, "abrp": 60},
    "is_reservable": {"sharinet": 85, "ocm": 50, "abrp": 45},
}


def claim(provenance: dict, field: str, source: str, now: datetime | None = None) -> bool:
    """Return True when this source may write the canonical field."""
    priority = FIELD_PRIORITY.get(field, {}).get(source, 0)
    current = provenance.get(field) or {}
    if current and int(current.get("priority", 0)) > priority:
        return False
    provenance[field] = {
        "source": source,
        "priority": priority,
        "at": (now or datetime.now(UTC)).isoformat(),
    }
    return True
