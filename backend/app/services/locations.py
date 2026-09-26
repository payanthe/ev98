from __future__ import annotations

import math
from datetime import datetime

from sqlalchemy import and_, or_, select
from sqlalchemy.orm import selectinload

from app.domain.connectors import power_family
from app.domain.hours import resolve_hours
from app.domain.status import AVAILABILITY_LABELS, STANDARD_LABELS, STATUS_LABELS, summarize_statuses

# Most → least common in live charging.connectors inventory.
_STANDARD_ORDER = {
    "CCS_2": 0,
    "GBT_DC": 1,
    "GBT_AC": 2,
    "TYPE_2": 3,
    "CHADEMO": 4,
    "TYPE_1": 5,
}
from app.domain.text import haversine_m, normalize_fa
from app.models.base import utcnow
from app.models.entities import Address, ChargingPool, Evse, ExternalRecord, Location
from app.schemas.api import (
    ConnectorOut,
    CountsOut,
    EvseOut,
    LocationDetail,
    MapLocation,
    MapResponse,
    PriceOut,
    SourceNoteOut,
    SourceOut,
)


def _load_options():
    return (
        selectinload(Location.operator),
        selectinload(Location.address),
        selectinload(Location.prices),
        selectinload(Location.pools).selectinload(ChargingPool.evses).selectinload(Evse.connectors),
    )


def active_evses(location: Location) -> list[Evse]:
    return [evse for pool in location.pools for evse in pool.evses if evse.withdrawn_at is None]


def _watts_to_kw(watts: int | None) -> float | None:
    if not watts:
        return None
    return round(watts / 1000, 1)


def _max_power_kw(evses: list[Evse]) -> float | None:
    watts = [evse.max_power_w for evse in evses if evse.max_power_w]
    watts.extend(connector.max_power_w for evse in evses for connector in evse.connectors if connector.max_power_w)
    if not watts:
        return None
    return round(max(watts) / 1000, 1)


def _standards(evses: list[Evse]) -> list[str]:
    seen: list[str] = []
    for evse in evses:
        for connector in evse.connectors:
            if connector.standard not in seen:
                seen.append(connector.standard)
    return sorted(seen, key=lambda item: _STANDARD_ORDER.get(item, 99))


def _power_types(evses: list[Evse]) -> list[str]:
    found: list[str] = []
    for evse in evses:
        for connector in evse.connectors:
            family = power_family(connector.power_type)
            if family and family not in found:
                found.append(family)
    return found


def _availability(evses: list[Evse], now) -> tuple[str, bool]:
    items = [
        (evse.status, evse.status_kind, evse.status_expires_at, evse.withdrawn_at)
        for evse in evses
    ]
    # withdrawn evses are already filtered; pass None for withdrawn_at
    return summarize_statuses([(status, kind, expires, None) for status, kind, expires, _ in items], now)


def _connector_totals(evses: list[Evse]) -> tuple[int | None, int | None]:
    detailed = [connector for evse in evses for connector in evse.connectors]
    if detailed and any(connector.status for connector in detailed):
        available = sum(1 for connector in detailed if connector.status == "AVAILABLE")
        return available, len(detailed)
    totals = [evse.reported_total for evse in evses if evse.reported_total is not None]
    available = [evse.reported_available for evse in evses if evse.reported_available is not None]
    if not totals and not available:
        return None, None
    return (sum(available) if available else None), (sum(totals) if totals else None)


def _matches(
    location: Location,
    evses: list[Evse],
    *,
    connectors: set[str],
    min_power_kw: float | None,
    sources: set[str],
    availability: str | None,
    now,
) -> bool:
    if sources and not sources.intersection(location.source_codes or []):
        return False
    standards = set(_standards(evses))
    if connectors and not connectors.intersection(standards):
        return False
    if min_power_kw is not None:
        power = _max_power_kw(evses)
        if power is None or power < min_power_kw:
            return False
    if availability:
        state, _stale = _availability(evses, now)
        if state != availability:
            return False
    return True


def _map_item(location: Location, now, distance_m: int | None = None) -> MapLocation:
    evses = active_evses(location)
    state, stale = _availability(evses, now)
    standards = _standards(evses)
    available, total = _connector_totals(evses)
    return MapLocation(
        id=location.id,
        name=location.canonical_name_fa,
        lat=float(location.latitude),
        lng=float(location.longitude),
        operator_name=location.operator.name if location.operator else None,
        city=location.address.city if location.address else None,
        max_power_kw=_max_power_kw(evses),
        connector_standards=standards,
        connector_labels=[STANDARD_LABELS.get(item, item) for item in standards],
        power_types=_power_types(evses),
        availability=state,
        availability_label=AVAILABILITY_LABELS.get(state, state),
        is_stale=stale,
        available_connectors=available,
        total_connectors=total,
        source_codes=list(location.source_codes or []),
        distance_m=distance_m,
    )


def search_locations(
    session,
    *,
    south: float | None,
    west: float | None,
    north: float | None,
    east: float | None,
    lat: float | None,
    lng: float | None,
    radius_m: int | None,
    q: str | None,
    connectors: list[str],
    min_power_kw: float | None,
    sources: list[str],
    availability: str | None,
    limit: int,
) -> MapResponse:
    stmt = select(Location).where(Location.deleted_at.is_(None)).options(*_load_options())
    # Lat/lng bounds keep the map query correct for Iran without a geography cast.
    # `coordinates` remains the canonical PostGIS point for later distance indexes.
    if south is not None and west is not None and north is not None and east is not None:
        stmt = stmt.where(Location.latitude.between(south, north), Location.longitude.between(west, east))
    elif lat is not None and lng is not None and radius_m is not None:
        delta_lat = radius_m / 111_000
        cos_lat = max(0.2, math.cos(math.radians(lat)))
        delta_lng = radius_m / (111_000 * cos_lat)
        stmt = stmt.where(
            Location.latitude.between(lat - delta_lat, lat + delta_lat),
            Location.longitude.between(lng - delta_lng, lng + delta_lng),
        )
    if q:
        token = normalize_fa(q)
        stmt = stmt.outerjoin(Address, Address.id == Location.address_id).where(
            or_(Location.name_normalized.ilike(f"%{token}%"), Address.formatted_address_fa.ilike(f"%{q}%"))
        )
    rows = session.scalars(stmt.limit(1500)).unique().all()
    truncated = len(rows) >= 1500
    now = utcnow()
    connector_set = set(connectors)
    source_set = set(sources)
    items: list[MapLocation] = []
    for location in rows:
        evses = active_evses(location)
        if not _matches(
            location,
            evses,
            connectors=connector_set,
            min_power_kw=min_power_kw,
            sources=source_set,
            availability=availability,
            now=now,
        ):
            continue
        distance = None
        if lat is not None and lng is not None:
            distance = int(haversine_m(lat, lng, float(location.latitude), float(location.longitude)))
            if radius_m is not None and distance > radius_m:
                continue
        items.append(_map_item(location, now, distance))
    if lat is not None and lng is not None:
        items.sort(key=lambda item: item.distance_m or 0)
    if len(items) > limit:
        truncated = True
        items = items[:limit]
    return MapResponse(items=items, count=len(items), truncated=truncated, limit=limit)


def _price(location: Location, evses: list[Evse]) -> PriceOut | None:
    active_ids = {evse.id for evse in evses}
    observations = [price for price in location.prices if price.evse_id in active_ids or price.evse_id is None]
    if not observations:
        return None
    observations.sort(key=lambda item: item.observed_at, reverse=True)
    latest = observations[0]
    amounts = {item.amount_minor for item in observations}
    return PriceOut(
        amount_rial=latest.amount_minor,
        amount_toman=latest.display_amount,
        currency=latest.currency,
        unit=latest.per_unit,
        label=latest.label,
        observed_at=latest.observed_at,
        source_code=latest.source_code,
        is_free=latest.amount_minor == 0,
        varies=len(amounts) > 1,
    )


def _evse_out(evse: Evse, now) -> EvseOut:
    stale = bool(evse.status_kind == "live" and evse.status_expires_at and evse.status_expires_at <= now)
    counts = None
    if evse.reported_total is not None or evse.reported_available is not None:
        counts = CountsOut(
            total=evse.reported_total,
            available=evse.reported_available,
            charging=evse.reported_charging,
            unavailable=evse.reported_unavailable,
        )
    connectors = [
        ConnectorOut(
            id=connector.id,
            index=connector.connector_index,
            standard=connector.standard,
            standard_label=STANDARD_LABELS.get(connector.standard, connector.standard),
            power_type=connector.power_type,
            format=connector.format,
            max_power_kw=_watts_to_kw(connector.max_power_w),
            status=connector.status,
            status_label=STATUS_LABELS.get(connector.status or "", None),
            raw_name=connector.raw_name,
        )
        for connector in sorted(evse.connectors, key=lambda item: item.connector_index)
    ]
    return EvseOut(
        id=evse.id,
        external_id=evse.origin_external_id,
        source_code=evse.origin_source_code,
        status="STALE" if stale else evse.status,
        status_label="وضعیت منقضی" if stale else STATUS_LABELS.get(evse.status, evse.status),
        status_kind=evse.status_kind,
        reported_status=evse.reported_status,
        reported_status_label=STATUS_LABELS.get(evse.reported_status or "", None),
        status_updated_at=evse.status_updated_at,
        status_expires_at=evse.status_expires_at,
        is_stale=stale,
        max_power_kw=_watts_to_kw(evse.max_power_w),
        counts=counts,
        connectors=connectors,
    )


def _notes(location: Location) -> list[SourceNoteOut]:
    notes: list[SourceNoteOut] = []
    for item in location.source_notes or []:
        if not isinstance(item, dict):
            continue
        text = " ".join(str(item.get("text") or "").split())
        source = str(item.get("source") or "").strip()
        if not text or not source:
            continue
        kind = item.get("kind") if item.get("kind") in {"access", "notice"} else "access"
        observed = item.get("observed_at")
        parsed = None
        if isinstance(observed, str) and observed:
            try:
                parsed = datetime.fromisoformat(observed.replace("Z", "+00:00"))
            except ValueError:
                parsed = None
        notes.append(SourceNoteOut(source_code=source, kind=kind, text=text, observed_at=parsed))
    notes.sort(key=lambda note: (0 if note.kind == "access" else 1, note.source_code, note.text))
    return notes


def get_location(session, location_id) -> LocationDetail | None:
    location = session.scalar(
        select(Location).where(Location.id == location_id, Location.deleted_at.is_(None)).options(*_load_options())
    )
    if location is None:
        return None
    now = utcnow()
    evses = active_evses(location)
    state, stale = _availability(evses, now)
    evse_ids = [evse.id for pool in location.pools for evse in pool.evses]
    clauses = [
        and_(
            ExternalRecord.canonical_entity_type == "location",
            ExternalRecord.canonical_entity_id == location.id,
        )
    ]
    if evse_ids:
        clauses.append(
            and_(ExternalRecord.canonical_entity_type == "evse", ExternalRecord.canonical_entity_id.in_(evse_ids))
        )
    records = session.scalars(
        select(ExternalRecord).where(or_(*clauses)).options(selectinload(ExternalRecord.source))
    ).all()
    sources = [
        SourceOut(
            code=record.source.code,
            name=record.source.name,
            external_id=record.external_id,
            attribution=record.attribution_text,
            last_seen_at=record.last_seen_at,
        )
        for record in records
        if record.is_present_at_source and record.source is not None
    ]
    images = [url for url in (location.image_urls or []) if str(url).startswith("https://")]
    hours = resolve_hours(
        hours_summary=location.hours_summary,
        is_24_7=location.is_24_7,
        hours_schedule=location.hours_schedule,
        now=now,
        timezone=location.timezone or "Asia/Tehran",
    )
    return LocationDetail(
        id=location.id,
        name=location.canonical_name_fa,
        name_en=location.canonical_name_en,
        operator_name=location.operator.name if location.operator else None,
        address=location.address.formatted_address_fa if location.address else None,
        city=location.address.city if location.address else None,
        province=location.address.province if location.address else None,
        lat=float(location.latitude),
        lng=float(location.longitude),
        phone=location.phone,
        website=location.website_url,
        is_public=location.is_public,
        is_24_7=hours.is_24_7,
        is_reservable=location.is_reservable,
        hours_summary=hours.hours_summary,
        hours_label=hours.hours_label,
        open_now=hours.open_now,
        open_now_label=hours.open_now_label,
        hours_schedule=hours.schedule,
        facilities=list(location.facilities or []),
        notes=_notes(location),
        images=images,
        availability=state,
        availability_label=AVAILABILITY_LABELS.get(state, state),
        is_stale=stale,
        max_power_kw=_max_power_kw(evses),
        source_codes=list(location.source_codes or []),
        sources=sources,
        evses=[_evse_out(evse, now) for evse in evses],
        price=_price(location, evses),
        field_provenance=dict(location.field_provenance or {}),
        data_quality_score=float(location.data_quality_score) if location.data_quality_score is not None else None,
        updated_at=location.updated_at,
    )
