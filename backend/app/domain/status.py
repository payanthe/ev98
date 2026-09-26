from datetime import datetime

AVAILABLE = "AVAILABLE"
CHARGING = "CHARGING"
UNAVAILABLE = "UNAVAILABLE"
UNKNOWN = "UNKNOWN"
OPERATIONAL = "OPERATIONAL"
OUT_OF_ORDER = "OUT_OF_ORDER"
REMOVED = "REMOVED"

AVAILABILITY_LABELS = {
    "available": "آزاد",
    "charging": "در حال شارژ",
    "unavailable": "خارج از دسترس",
    "stale": "وضعیت منقضی",
    "operational": "عملیاتی، بدون وضعیت زنده",
    "unknown": "نامشخص",
}

STATUS_LABELS = {
    AVAILABLE: "آزاد",
    CHARGING: "در حال شارژ",
    UNAVAILABLE: "خارج از دسترس",
    UNKNOWN: "نامشخص",
    OPERATIONAL: "عملیاتی",
    OUT_OF_ORDER: "خراب",
    REMOVED: "برچیده",
}

STANDARD_LABELS = {
    "TYPE_1": "Type 1",
    "TYPE_2": "Type 2",
    "CCS_1": "CCS1",
    "CCS_2": "CCS2",
    "CHADEMO": "CHAdeMO",
    "GBT_AC": "GB/T AC",
    "GBT_DC": "GB/T DC",
    "NACS": "NACS",
    "SCHUKO": "Schuko",
    "UNKNOWN": "نامشخص",
}

SHARINET_CHARGER_STATUS = {
    "available": AVAILABLE,
    "charging": CHARGING,
    "unavailable": UNAVAILABLE,
}

OCM_STATUS = {
    0: (UNKNOWN, "operational"),
    10: (AVAILABLE, "live"),
    20: (CHARGING, "live"),
    30: (UNAVAILABLE, "live"),
    50: (OPERATIONAL, "operational"),
    75: (OPERATIONAL, "operational"),
    100: (OUT_OF_ORDER, "operational"),
    150: (UNKNOWN, "operational"),
    200: (REMOVED, "operational"),
    210: (REMOVED, "operational"),
}

ABRP_STATUS = {
    "AVAILABLE": AVAILABLE,
    "FREE": AVAILABLE,
    "CHARGING": CHARGING,
    "OCCUPIED": CHARGING,
    "IN_USE": CHARGING,
    "RESERVED": CHARGING,
    "UNKNOWN": UNKNOWN,
    "OUT_OF_ORDER": OUT_OF_ORDER,
    "INOPERATIVE": OUT_OF_ORDER,
    "BLOCKED": UNAVAILABLE,
    "UNAVAILABLE": UNAVAILABLE,
}


def map_sharinet_charger_status(value: str | None) -> str:
    return SHARINET_CHARGER_STATUS.get((value or "").strip().lower(), UNKNOWN)


def map_sharinet_connector_status(status: str | None, status_code: object) -> str | None:
    text = (status or "").replace("\u200c", "").replace(" ", "")
    if status_code in (1, "1") or "دردسترس" in text:
        return AVAILABLE
    if status_code in (2, "2") or "شارژ" in text:
        return CHARGING
    if status_code in (3, "3") or "خارجازدسترس" in text:
        return UNAVAILABLE
    return None


def derive_from_counts(counts: dict | None) -> str | None:
    if not counts:
        return None
    available = int(counts.get("available") or 0)
    charging = int(counts.get("charging") or 0)
    unavailable = int(counts.get("unavailable") or 0)
    if available > 0:
        return AVAILABLE
    if charging > 0:
        return CHARGING
    if unavailable > 0:
        return UNAVAILABLE
    return None


def derive_from_connector_statuses(statuses: list[str | None]) -> str | None:
    known = [status for status in statuses if status]
    if not known:
        return None
    if AVAILABLE in known:
        return AVAILABLE
    if CHARGING in known:
        return CHARGING
    if known and all(status == UNAVAILABLE for status in known):
        return UNAVAILABLE
    return UNKNOWN


def derive_sharinet_status(
    charger_status: str | None,
    counts: dict | None,
    connector_statuses: list[str | None] | None = None,
) -> str:
    from_connectors = derive_from_connector_statuses(connector_statuses or [])
    if from_connectors:
        return from_connectors
    from_counts = derive_from_counts(counts)
    if from_counts:
        return from_counts
    return map_sharinet_charger_status(charger_status)


def summarize_statuses(
    items: list[tuple[str, str, datetime | None, datetime | None]],
    now: datetime,
) -> tuple[str, bool]:
    """Summarize (status, kind, expires_at, withdrawn_at) into a map pin state."""
    active = [item for item in items if item[3] is None]
    if not active:
        return "unknown", False

    fresh: list[str] = []
    stale = 0
    operational = 0
    for status, kind, expires_at, _withdrawn in active:
        if kind == "live":
            if expires_at is not None and expires_at <= now:
                stale += 1
            else:
                fresh.append(status)
        elif status == OPERATIONAL:
            operational += 1

    if fresh:
        if AVAILABLE in fresh:
            return "available", False
        if CHARGING in fresh:
            return "charging", False
        if all(status in {UNAVAILABLE, OUT_OF_ORDER} for status in fresh):
            return "unavailable", False
        return "unknown", False
    if stale:
        return "stale", True
    if operational:
        return "operational", False
    return "unknown", False
