"""Write normalized source records onto canonical locations without dropping raw payloads."""

from __future__ import annotations

import hashlib
import json
import math
import re
import uuid
from datetime import timedelta
from decimal import Decimal

from geoalchemy2.elements import WKTElement
from sqlalchemy import and_, delete, or_, select
from sqlalchemy.orm import selectinload
from sqlalchemy.orm.attributes import flag_modified

from app.core.config import settings
from app.domain.priority import claim
from app.domain.provinces import province_at
from app.domain.slugs import station_slug
from app.domain.text import normalize_fa, toman_to_rial
from app.ingestion.matching import LocationIdentity, MatchEvidence, match_locations
from app.ingestion.records import NormalizedConnector, NormalizedEvse, NormalizedNote, NormalizedRecord, normalized_dict
from app.models.base import utcnow
from app.models.entities import (
    Address,
    ChargingPool,
    Connector,
    Evse,
    ExternalLink,
    ExternalRecord,
    Location,
    Operator,
    PriceObservation,
    SourceSystem,
)

POOL_NAMES = {"sharinet": "شارینت", "ocm": "Open Charge Map", "abrp": "ABRP"}


def as_coord(value: float) -> Decimal:
    return Decimal(str(round(float(value), 7)))


def point(lng: float, lat: float) -> WKTElement:
    return WKTElement(f"POINT({float(lng)} {float(lat)})", srid=4326)


_CANONICAL_OPERATORS: dict[str, tuple[str, tuple[str, ...]]] = {
    "mapna": ("مپنا", ("مپنا", "شارینت", "mapna", "emapna", "empana", "sharinet")),
    "xvision": ("ایکس ویژن", ("ایکس ویژن", "ایکسویژن", "xvision", "xv go", "xvgo")),
}


def operator_slug(name: str) -> str:
    normalized = normalize_fa(name).lower()
    for slug, (_label, tokens) in _CANONICAL_OPERATORS.items():
        if any(token in normalized for token in tokens):
            return slug
    ascii_part = re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")
    if ascii_part:
        return ascii_part[:60]
    return "op-" + hashlib.sha1(name.encode()).hexdigest()[:10]


def content_hash(payload: dict) -> str:
    blob = json.dumps(payload, sort_keys=True, ensure_ascii=False, default=str)
    return hashlib.sha256(blob.encode()).hexdigest()


def get_source(session, code: str) -> SourceSystem:
    source = session.scalar(select(SourceSystem).where(SourceSystem.code == code))
    if source is None:
        raise RuntimeError(f"source {code} is not registered")
    return source


def get_operator(session, name: str) -> Operator:
    slug = operator_slug(name)
    canonical = _CANONICAL_OPERATORS.get(slug)
    canonical_name = canonical[0] if canonical else name
    operator = session.scalar(select(Operator).where(Operator.slug == slug))
    if operator is None:
        operator = Operator(slug=slug, name=canonical_name)
        session.add(operator)
        session.flush()
    elif operator.name != canonical_name and slug in _CANONICAL_OPERATORS:
        operator.name = canonical_name
    return operator


def unique_slug(session, source_code: str, external_id: str, name: str, lat: float, lng: float) -> str:
    del source_code, external_id
    base = station_slug(name, province_at(lat, lng))
    slug = base
    suffix = 2
    while session.scalar(select(Location.id).where(Location.slug == slug)):
        slug = f"{base}-{suffix}"
        suffix += 1
    return slug


def new_location(session, source_code: str, external_id: str, name: str, lat: float, lng: float) -> Location:
    location = Location(
        slug=unique_slug(session, source_code, external_id, name, lat, lng),
        canonical_name_fa=name,
        name_normalized=normalize_fa(name),
        publish_status="published",
        timezone="Asia/Tehran",
        latitude=as_coord(lat),
        longitude=as_coord(lng),
        coordinates=point(lng, lat),
        field_provenance={},
        facilities=[],
        source_notes=[],
        image_urls=[],
        source_codes=[],
        access_type="unknown",
    )
    session.add(location)
    session.flush()
    return location


def apply_location_fields(session, location: Location, source_code: str, record: NormalizedRecord, lat: float, lng: float) -> None:
    provenance = dict(location.field_provenance or {})
    if record.name and claim(provenance, "canonical_name_fa", source_code):
        location.canonical_name_fa = record.name
        location.name_normalized = normalize_fa(record.name)
        if record.name_en:
            location.canonical_name_en = record.name_en
    if claim(provenance, "coordinates", source_code):
        location.latitude = as_coord(lat)
        location.longitude = as_coord(lng)
        location.coordinates = point(lng, lat)
    if record.address and claim(provenance, "address", source_code):
        address = location.address or session.get(Address, location.address_id) if location.address_id else None
        if address is None:
            address = Address(country_code="IR")
            session.add(address)
            session.flush()
            location.address_id = address.id
        address.formatted_address_fa = record.address
        address.province = record.province
        address.city = record.city
        address.country_code = "IR"
    if record.phone and claim(provenance, "phone", source_code):
        location.phone = record.phone
    if record.website and claim(provenance, "website", source_code):
        location.website_url = record.website
    if record.operator_name and claim(provenance, "operator", source_code):
        location.operator_id = get_operator(session, record.operator_name).id
    if record.is_public is not None and claim(provenance, "is_public", source_code):
        location.is_public = record.is_public
        location.access_type = record.access_type
    if record.is_24_7 is not None and claim(provenance, "is_24_7", source_code):
        location.is_24_7 = record.is_24_7
    if record.hours_summary and claim(provenance, "hours_summary", source_code):
        location.hours_summary = record.hours_summary
        if record.hours_schedule:
            location.hours_schedule = dict(record.hours_schedule)
            flag_modified(location, "hours_schedule")
            claim(provenance, "hours_schedule", source_code)
        elif claim(provenance, "hours_schedule", source_code):
            location.hours_schedule = None
    elif record.hours_schedule and claim(provenance, "hours_schedule", source_code):
        location.hours_schedule = dict(record.hours_schedule)
        flag_modified(location, "hours_schedule")
    if record.facilities and claim(provenance, "facilities", source_code):
        location.facilities = list(record.facilities)
    if record.image_urls and claim(provenance, "images", source_code):
        location.image_urls = list(record.image_urls)
    if record.is_reservable is not None and claim(provenance, "is_reservable", source_code):
        location.is_reservable = record.is_reservable
    replace_source_notes(location, source_code, record.notes)
    location.field_provenance = provenance
    flag_modified(location, "field_provenance")
    location.updated_at = utcnow()


def replace_source_notes(location: Location, source_code: str, notes: list[NormalizedNote]) -> None:
    """Replace one source's notes and keep every other source."""
    kept = [item for item in (location.source_notes or []) if isinstance(item, dict) and item.get("source") != source_code]
    seen = {normalize_fa(str(item.get("text") or "")) for item in kept}
    for note in notes:
        text = " ".join(note.text.split())
        key = normalize_fa(text)
        if not key or key in seen:
            continue
        seen.add(key)
        observed = note.observed_at.isoformat() if note.observed_at else None
        kept.append(
            {
                "source": source_code,
                "kind": note.kind if note.kind in {"access", "notice"} else "access",
                "text": text,
                "observed_at": observed,
            }
        )
    location.source_notes = kept
    flag_modified(location, "source_notes")


def pool_for(session, location: Location, source_code: str) -> ChargingPool:
    pool = session.scalar(
        select(ChargingPool).where(
            ChargingPool.location_id == location.id,
            ChargingPool.origin_source_code == source_code,
        )
    )
    if pool is None:
        pool = ChargingPool(
            location_id=location.id,
            origin_source_code=source_code,
            name=POOL_NAMES.get(source_code, source_code),
        )
        session.add(pool)
        session.flush()
    else:
        pool.deleted_at = None
    return pool


def upsert_external(
    session,
    source: SourceSystem,
    record: NormalizedRecord,
    *,
    canonical_type: str | None,
    canonical_id: uuid.UUID | None,
    entity_type: str | None = None,
) -> ExternalRecord:
    entity_type = entity_type or record.entity_type
    ext = session.scalar(
        select(ExternalRecord).where(
            ExternalRecord.source_system_id == source.id,
            ExternalRecord.entity_type == entity_type,
            ExternalRecord.external_id == record.external_id,
        )
    )
    now = utcnow()
    if ext is None:
        ext = ExternalRecord(
            source_system_id=source.id,
            entity_type=entity_type,
            external_id=record.external_id,
            first_seen_at=now,
        )
        session.add(ext)
    ext.raw_payload = record.raw or {}
    ext.normalized_payload = normalized_dict(record)
    ext.content_hash = content_hash(ext.raw_payload or {})
    ext.canonical_entity_type = canonical_type
    ext.canonical_entity_id = canonical_id
    ext.is_present_at_source = bool(record.publish)
    ext.validation_status = "valid" if record.publish else "withdrawn"
    ext.validation_errors = None
    ext.attribution_text = record.attribution
    ext.last_seen_at = now
    ext.last_fetched_at = now
    session.flush()
    return ext


def upsert_evse(session, pool: ChargingPool, existing: Evse | None, evse_norm: NormalizedEvse, source_code: str) -> Evse:
    now = utcnow()
    expires = now + timedelta(seconds=settings.status_ttl_seconds) if evse_norm.status_kind == "live" else None
    if existing is None:
        existing = session.scalar(
            select(Evse).where(
                Evse.origin_source_code == source_code,
                Evse.origin_external_id == evse_norm.external_id,
            )
        )
    if existing is None:
        existing = Evse(
            pool_id=pool.id,
            origin_source_code=source_code,
            origin_external_id=evse_norm.external_id,
        )
        session.add(existing)
    existing.pool_id = pool.id
    existing.physical_reference = evse_norm.physical_reference
    existing.status = evse_norm.status
    existing.status_kind = evse_norm.status_kind
    existing.reported_status = evse_norm.reported_status
    existing.status_updated_at = now
    existing.status_expires_at = expires
    existing.max_power_w = evse_norm.max_power_w
    existing.withdrawn_at = None
    counts = evse_norm.counts or {}
    existing.reported_total = counts.get("total")
    existing.reported_available = counts.get("available")
    existing.reported_charging = counts.get("charging")
    existing.reported_unavailable = counts.get("unavailable")
    session.flush()
    return existing


def replace_connectors(session, evse: Evse, connectors: list[NormalizedConnector]) -> None:
    session.execute(delete(Connector).where(Connector.evse_id == evse.id))
    session.flush()
    used: set[int] = set()
    for item in connectors:
        index = item.index
        while index in used:
            index += 1
        used.add(index)
        session.add(
            Connector(
                evse_id=evse.id,
                connector_index=index,
                standard=item.standard,
                format=item.format,
                power_type=item.power_type,
                max_power_w=item.max_power_w,
                status=item.status,
                raw_name=item.raw_name,
            )
        )
    session.flush()


def upsert_price(session, location_id: uuid.UUID, evse_id: uuid.UUID, record: NormalizedRecord) -> None:
    if record.price_toman_per_kwh is None and not record.is_free:
        return
    toman = 0 if record.is_free else int(record.price_toman_per_kwh or 0)
    rial = toman_to_rial(toman)
    observed = record.price_observed_at or utcnow()
    latest = session.scalar(
        select(PriceObservation)
        .where(PriceObservation.evse_id == evse_id, PriceObservation.source_code == record.source_code)
        .order_by(PriceObservation.observed_at.desc())
    )
    if latest and latest.amount_minor == rial and latest.label == record.price_label:
        latest.observed_at = observed
        return
    session.add(
        PriceObservation(
            location_id=location_id,
            evse_id=evse_id,
            source_code=record.source_code,
            amount_minor=rial,
            currency="IRR",
            per_unit="kwh",
            display_amount=toman,
            display_unit="toman",
            label=record.price_label,
            observed_at=observed,
        )
    )


def iter_evses(session, location_id: uuid.UUID) -> list[Evse]:
    pools = session.scalars(
        select(ChargingPool)
        .where(ChargingPool.location_id == location_id)
        .options(selectinload(ChargingPool.evses).selectinload(Evse.connectors))
    ).all()
    return [evse for pool in pools for evse in pool.evses]


def recompute_source_codes(session, location: Location) -> None:
    evses = iter_evses(session, location.id)
    codes = {evse.origin_source_code for evse in evses if evse.withdrawn_at is None}
    evse_ids = [evse.id for evse in evses]
    clauses = [
        and_(
            ExternalRecord.canonical_entity_type == "location",
            ExternalRecord.canonical_entity_id == location.id,
            ExternalRecord.is_present_at_source.is_(True),
        )
    ]
    if evse_ids:
        clauses.append(
            and_(
                ExternalRecord.canonical_entity_type == "evse",
                ExternalRecord.canonical_entity_id.in_(evse_ids),
                ExternalRecord.is_present_at_source.is_(True),
            )
        )
    source_ids = set(session.scalars(select(ExternalRecord.source_system_id).where(or_(*clauses))).all())
    if source_ids:
        codes.update(session.scalars(select(SourceSystem.code).where(SourceSystem.id.in_(source_ids))).all())
    location.source_codes = sorted(codes)


def score_location(session, location: Location) -> Decimal:
    evses = [evse for evse in iter_evses(session, location.id) if evse.withdrawn_at is None]
    score = 25
    if location.address_id:
        score += 20
    if any(evse.max_power_w for evse in evses) or any(
        connector.max_power_w for evse in evses for connector in evse.connectors
    ):
        score += 20
    if location.facilities:
        score += 10
    if any(evse.status_kind == "live" for evse in evses):
        score += 15
    if location.source_codes and len(list(location.source_codes)) > 1:
        score += 10
    return Decimal(min(score, 100))


def hide_if_empty(session, location: Location) -> None:
    evses = iter_evses(session, location.id)
    if any(evse.withdrawn_at is None for evse in evses):
        if location.deleted_at is not None:
            location.deleted_at = None
        location.publish_status = "published"
        return
    location.deleted_at = utcnow()
    location.publish_status = "withdrawn"


def hide_empty_locations(session) -> int:
    hidden = 0
    for location in session.scalars(select(Location).where(Location.deleted_at.is_(None))).all():
        hide_if_empty(session, location)
        if location.deleted_at is not None:
            hidden += 1
    return hidden


def _richest(members: list[NormalizedRecord]) -> NormalizedRecord:
    def score(item: NormalizedRecord) -> tuple[int, int, int, int]:
        return (
            int(bool(item.address)),
            int(bool(item.facilities)),
            int(item.price_toman_per_kwh is not None or item.is_free),
            int(bool(item.image_urls)),
        )

    return max(members, key=score)


def _centroid(members: list[NormalizedRecord]) -> tuple[float, float]:
    return (
        sum(item.lat for item in members) / len(members),
        sum(item.lng for item in members) / len(members),
    )


def _identity_from_record(record: NormalizedRecord, lat: float | None = None, lng: float | None = None) -> LocationIdentity:
    return LocationIdentity(
        name=record.name,
        lat=record.lat if lat is None else lat,
        lng=record.lng if lng is None else lng,
        address=record.address,
        operator_name=record.operator_name,
    )


def _identity_from_location(location: Location) -> LocationIdentity:
    return LocationIdentity(
        name=location.canonical_name_fa,
        lat=float(location.latitude),
        lng=float(location.longitude),
        address=location.address.formatted_address_fa if location.address else None,
        operator_name=location.operator.name if location.operator else None,
    )


def find_cross_source_match(
    session,
    record: NormalizedRecord,
    counterpart_source: str,
    *,
    lat: float | None = None,
    lng: float | None = None,
) -> tuple[Location, MatchEvidence] | None:
    """Find one unambiguous, high-confidence location owned by another source."""
    identity = _identity_from_record(record, lat, lng)
    # Cheap bounding box before the exact Haversine gate in match_locations.
    lat_delta = 250 / 111_000
    lng_delta = 250 / max(1.0, 111_000 * abs(math.cos(math.radians(identity.lat))))
    candidates = session.scalars(
        select(Location)
        .where(
            Location.deleted_at.is_(None),
            Location.latitude.between(identity.lat - lat_delta, identity.lat + lat_delta),
            Location.longitude.between(identity.lng - lng_delta, identity.lng + lng_delta),
        )
        .options(selectinload(Location.address), selectinload(Location.operator))
    ).all()
    matches: list[tuple[Location, MatchEvidence]] = []
    for candidate in candidates:
        if counterpart_source not in set(candidate.source_codes or []):
            continue
        evidence = match_locations(identity, _identity_from_location(candidate))
        if evidence is not None:
            matches.append((candidate, evidence))
    matches.sort(key=lambda item: (item[1].confidence, -item[1].distance_m), reverse=True)
    if not matches:
        return None
    # Do not auto-merge when two nearby candidates are almost equally plausible.
    if len(matches) > 1 and matches[0][1].confidence - matches[1][1].confidence < 0.05:
        return None
    return matches[0]


def _absorb_catalog_location(
    session, target: Location, duplicate: Location, source_code: str
) -> list[ExternalRecord]:
    """Move catalog assertions to target and retire only their duplicate hardware."""
    source = session.scalar(select(SourceSystem).where(SourceSystem.code == source_code))
    if source is None:
        return []
    records = session.scalars(
        select(ExternalRecord).where(
            ExternalRecord.source_system_id == source.id,
            ExternalRecord.canonical_entity_type == "location",
            ExternalRecord.canonical_entity_id == duplicate.id,
        )
    ).all()
    for external in records:
        if source_code == "ocm" and external.raw_payload:
            # Re-apply complementary OCM fields (for example phone) using the
            # normal field-priority rules before moving its identity.
            from app.ingestion.adapters.ocm import normalize_poi

            normalized = normalize_poi(external.raw_payload)
            if normalized is not None:
                apply_location_fields(
                    session, target, source_code, normalized, normalized.lat, normalized.lng
                )
        external.canonical_entity_id = target.id
    withdraw_source_evses(session, duplicate, source_code, clear_notes=False)
    recompute_source_codes(session, duplicate)
    hide_if_empty(session, duplicate)
    return records


def persist_sharinet_cluster(session, source: SourceSystem, members: list[NormalizedRecord]) -> Location:
    ids = [item.external_id for item in members]
    existing = session.scalars(
        select(Evse)
        .where(Evse.origin_source_code == "sharinet", Evse.origin_external_id.in_(ids))
        .options(selectinload(Evse.pool))
    ).all()
    by_external = {evse.origin_external_id: evse for evse in existing}
    location_ids = {evse.pool.location_id for evse in existing if evse.pool is not None}
    location = None
    if location_ids:
        location = session.scalar(select(Location).where(Location.id.in_(location_ids)).order_by(Location.created_at.asc()))
    lat, lng = _centroid(members)
    anchor = min(ids)
    primary = _richest(members)
    matched = find_cross_source_match(session, primary, "ocm", lat=lat, lng=lng)
    if matched is not None:
        matched_location = matched[0]
        if location is None:
            location = matched_location
        elif location.id != matched_location.id:
            _absorb_catalog_location(session, location, matched_location, "ocm")
    if location is None:
        location = new_location(session, "sharinet", anchor, primary.name, lat, lng)
    location.deleted_at = None
    location.publish_status = "published"
    if any(member.is_reservable for member in members):
        primary.is_reservable = True
    primary.notes = _merge_notes(members)
    apply_location_fields(session, location, "sharinet", primary, lat, lng)
    pool = pool_for(session, location, "sharinet")
    for member in members:
        evse_norm = member.evses[0]
        evse = upsert_evse(session, pool, by_external.get(member.external_id), evse_norm, "sharinet")
        if member.detail_fetched:
            replace_connectors(session, evse, evse_norm.connectors)
            upsert_price(session, location.id, evse.id, member)
        upsert_external(session, source, member, canonical_type="evse", canonical_id=evse.id, entity_type="charge_point")
    # OCM models the whole site as a synthetic EVSE. Once operator-grade
    # Sharinet hardware exists, keep OCM as metadata only to avoid double counts.
    withdraw_source_evses(session, location, "ocm", clear_notes=False)
    if matched is not None:
        link_same_site_records(session, location, matched[1])
    recompute_source_codes(session, location)
    location.data_quality_score = score_location(session, location)
    return location


def _location_from_external(session, source: SourceSystem, record: NormalizedRecord) -> Location | None:
    ext = session.scalar(
        select(ExternalRecord).where(
            ExternalRecord.source_system_id == source.id,
            ExternalRecord.entity_type == "location",
            ExternalRecord.external_id == record.external_id,
            ExternalRecord.canonical_entity_type == "location",
            ExternalRecord.canonical_entity_id.is_not(None),
        )
    )
    if ext is None or ext.canonical_entity_id is None:
        return None
    return session.get(Location, ext.canonical_entity_id)


def find_location_for_ocm(session, ocm_id: str) -> Location | None:
    ocm = session.scalar(select(SourceSystem).where(SourceSystem.code == "ocm"))
    if ocm is not None:
        ext = session.scalar(
            select(ExternalRecord).where(
                ExternalRecord.source_system_id == ocm.id,
                ExternalRecord.entity_type == "location",
                ExternalRecord.external_id == ocm_id,
                ExternalRecord.canonical_entity_id.is_not(None),
            )
        )
        if ext is not None and ext.canonical_entity_id is not None:
            location = session.get(Location, ext.canonical_entity_id)
            if location is not None:
                return location
    waiting = session.scalar(
        select(ExternalRecord).where(
            ExternalRecord.normalized_payload["ocm_external_id"].astext == ocm_id,
            ExternalRecord.canonical_entity_type == "location",
            ExternalRecord.canonical_entity_id.is_not(None),
        )
    )
    if waiting is not None and waiting.canonical_entity_id is not None:
        return session.get(Location, waiting.canonical_entity_id)
    return None


def _active_sources(session, location: Location) -> set[str]:
    return {evse.origin_source_code for evse in iter_evses(session, location.id) if evse.withdrawn_at is None}


def _merge_notes(members: list[NormalizedRecord]) -> list[NormalizedNote]:
    merged: list[NormalizedNote] = []
    seen: set[str] = set()
    for member in members:
        for note in member.notes:
            key = normalize_fa(note.text)
            if not key or key in seen:
                continue
            seen.add(key)
            merged.append(note)
    return merged


def withdraw_source_evses(
    session, location: Location, source_code: str, *, clear_notes: bool = True
) -> None:
    now = utcnow()
    if clear_notes:
        replace_source_notes(location, source_code, [])
    pools = session.scalars(
        select(ChargingPool)
        .where(ChargingPool.location_id == location.id, ChargingPool.origin_source_code == source_code)
        .options(selectinload(ChargingPool.evses))
    ).all()
    for pool in pools:
        for evse in pool.evses:
            evse.withdrawn_at = now


def _withdraw_unseen_evses(session, pool: ChargingPool, seen: set[str]) -> None:
    now = utcnow()
    for evse in session.scalars(select(Evse).where(Evse.pool_id == pool.id)).all():
        if evse.origin_external_id not in seen:
            evse.withdrawn_at = now


def link_records(
    session,
    left: ExternalRecord,
    right: ExternalRecord,
    evidence: dict,
    *,
    relation_type: str = "IMPORTED_FROM",
    confidence: Decimal = Decimal("1.0000"),
) -> None:
    exists = session.scalar(
        select(ExternalLink.id).where(
            ExternalLink.left_external_record_id == left.id,
            ExternalLink.right_external_record_id == right.id,
            ExternalLink.relation_type == relation_type,
        )
    )
    if exists is None:
        session.add(
            ExternalLink(
                left_external_record_id=left.id,
                right_external_record_id=right.id,
                relation_type=relation_type,
                confidence=confidence,
                evidence=evidence,
            )
        )


def link_same_site_records(session, location: Location, evidence: MatchEvidence) -> None:
    """Keep auditable source-to-source evidence without treating it as a validation error."""
    ocm = session.scalar(select(SourceSystem).where(SourceSystem.code == "ocm"))
    sharinet = session.scalar(select(SourceSystem).where(SourceSystem.code == "sharinet"))
    if ocm is None or sharinet is None:
        return
    ocm_records = session.scalars(
        select(ExternalRecord).where(
            ExternalRecord.source_system_id == ocm.id,
            ExternalRecord.canonical_entity_type == "location",
            ExternalRecord.canonical_entity_id == location.id,
            ExternalRecord.is_present_at_source.is_(True),
        )
    ).all()
    evse_ids = [evse.id for evse in iter_evses(session, location.id) if evse.origin_source_code == "sharinet"]
    if not evse_ids:
        return
    sharinet_records = session.scalars(
        select(ExternalRecord).where(
            ExternalRecord.source_system_id == sharinet.id,
            ExternalRecord.canonical_entity_type == "evse",
            ExternalRecord.canonical_entity_id.in_(evse_ids),
            ExternalRecord.is_present_at_source.is_(True),
        )
    ).all()
    confidence = Decimal(str(round(evidence.confidence, 4)))
    for left in ocm_records:
        for right in sharinet_records:
            link_records(
                session,
                left,
                right,
                evidence.as_dict(),
                relation_type="SAME_SITE",
                confidence=confidence,
            )


def _overlay_live_status(session, location: Location, record: NormalizedRecord) -> None:
    if not record.has_dynamic_status or not record.evses:
        return
    incoming = record.evses[0]
    if incoming.status_kind != "live":
        return
    now = utcnow()
    expires = now + timedelta(seconds=settings.status_ttl_seconds)
    for evse in iter_evses(session, location.id):
        if evse.withdrawn_at is None and evse.origin_source_code != "abrp":
            evse.status = incoming.status
            evse.status_kind = "live"
            evse.status_updated_at = now
            evse.status_expires_at = expires


def persist_catalog_record(session, source: SourceSystem, record: NormalizedRecord) -> None:
    location = _location_from_external(session, source, record)
    duplicate_location = None
    cross_match = None
    if record.source_code == "ocm":
        linked = find_location_for_ocm(session, record.external_id)
        if linked is not None:
            location = linked
        cross_match = find_cross_source_match(session, record, "sharinet")
        if cross_match is not None and (location is None or cross_match[0].id != location.id):
            duplicate_location = location
            location = cross_match[0]
    elif record.ocm_external_id:
        linked = find_location_for_ocm(session, record.ocm_external_id)
        if linked is not None:
            location = linked

    if not record.publish:
        upsert_external(
            session,
            source,
            record,
            canonical_type="location" if location is not None else None,
            canonical_id=location.id if location is not None else None,
        )
        if location is not None:
            withdraw_source_evses(session, location, record.source_code)
            recompute_source_codes(session, location)
            hide_if_empty(session, location)
        return

    if location is None:
        location = new_location(session, record.source_code, record.external_id, record.name, record.lat, record.lng)
    location.deleted_at = None
    location.publish_status = "published"
    apply_location_fields(session, location, record.source_code, record, record.lat, record.lng)

    active = _active_sources(session, location)
    abrp_overlay = record.source_code == "abrp" and "ocm" in active
    if record.source_code == "ocm" and "abrp" in active and "ocm" not in active:
        withdraw_source_evses(session, location, "abrp")

    ext = upsert_external(session, source, record, canonical_type="location", canonical_id=location.id)
    if record.source_code == "ocm":
        waiting = session.scalars(
            select(ExternalRecord).where(ExternalRecord.normalized_payload["ocm_external_id"].astext == record.external_id)
        ).all()
        for other in waiting:
            if other.id != ext.id:
                link_records(session, other, ext, {"ocm_external_id": record.external_id})
    elif record.ocm_external_id:
        ocm = session.scalar(select(SourceSystem).where(SourceSystem.code == "ocm"))
        if ocm is not None:
            ocm_ext = session.scalar(
                select(ExternalRecord).where(
                    ExternalRecord.source_system_id == ocm.id,
                    ExternalRecord.entity_type == "location",
                    ExternalRecord.external_id == record.ocm_external_id,
                )
            )
            if ocm_ext is not None:
                link_records(session, ext, ocm_ext, {"ocm_external_id": record.ocm_external_id})

    sharinet_overlay = record.source_code == "ocm" and "sharinet" in _active_sources(session, location)
    if abrp_overlay:
        _overlay_live_status(session, location, record)
    elif sharinet_overlay:
        withdraw_source_evses(session, location, "ocm", clear_notes=False)
    else:
        pool = pool_for(session, location, record.source_code)
        seen: set[str] = set()
        for evse_norm in record.evses:
            evse = upsert_evse(session, pool, None, evse_norm, record.source_code)
            if record.detail_fetched:
                replace_connectors(session, evse, evse_norm.connectors)
            seen.add(evse_norm.external_id)
        _withdraw_unseen_evses(session, pool, seen)

    if duplicate_location is not None:
        withdraw_source_evses(session, duplicate_location, record.source_code, clear_notes=False)
        recompute_source_codes(session, duplicate_location)
        hide_if_empty(session, duplicate_location)

    if cross_match is not None:
        link_same_site_records(session, location, cross_match[1])

    recompute_source_codes(session, location)
    location.data_quality_score = score_location(session, location)


def withdraw_missing_charge_points(session, source: SourceSystem, seen_ids: set[str]) -> int:
    rows = session.scalars(
        select(ExternalRecord).where(
            ExternalRecord.source_system_id == source.id,
            ExternalRecord.entity_type == "charge_point",
            ExternalRecord.is_present_at_source.is_(True),
        )
    ).all()
    now = utcnow()
    missing = 0
    touched: set[uuid.UUID] = set()
    for row in rows:
        if row.external_id in seen_ids:
            continue
        row.is_present_at_source = False
        row.validation_status = "absent"
        missing += 1
        if row.canonical_entity_type == "evse" and row.canonical_entity_id is not None:
            evse = session.get(Evse, row.canonical_entity_id)
            if evse is not None:
                evse.withdrawn_at = now
                pool = session.get(ChargingPool, evse.pool_id)
                if pool is not None:
                    touched.add(pool.location_id)
    for location_id in touched:
        location = session.get(Location, location_id)
        if location is not None and source.code not in _active_sources(session, location):
            replace_source_notes(location, source.code, [])
    return missing


def withdraw_missing_locations(session, source: SourceSystem, seen_ids: set[str]) -> int:
    rows = session.scalars(
        select(ExternalRecord).where(
            ExternalRecord.source_system_id == source.id,
            ExternalRecord.entity_type == "location",
            ExternalRecord.is_present_at_source.is_(True),
        )
    ).all()
    missing = 0
    for row in rows:
        if row.external_id in seen_ids:
            continue
        row.is_present_at_source = False
        row.validation_status = "absent"
        missing += 1
        if row.canonical_entity_type == "location" and row.canonical_entity_id is not None:
            location = session.get(Location, row.canonical_entity_id)
            if location is not None:
                withdraw_source_evses(session, location, source.code)
                recompute_source_codes(session, location)
                hide_if_empty(session, location)
    return missing
