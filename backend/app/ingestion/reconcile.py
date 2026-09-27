"""Global, source-independent location reconciliation and review queue."""

from __future__ import annotations

import uuid
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.orm import selectinload

from app.ingestion.matching import LocationIdentity, MatchEvidence, assess_locations
from app.ingestion.persist import (
    iter_evses,
    recompute_source_codes,
    score_location,
    withdraw_source_evses,
)
from app.models.base import utcnow
from app.models.entities import (
    ChargingPool,
    DuplicateCandidate,
    ExternalRecord,
    Location,
    PriceObservation,
)


def _identity(location: Location) -> LocationIdentity:
    return LocationIdentity(
        location.canonical_name_fa,
        float(location.latitude),
        float(location.longitude),
        location.address.formatted_address_fa if location.address else None,
        location.operator.name if location.operator else None,
    )


def _pair_ids(left: Location, right: Location) -> tuple[uuid.UUID, uuid.UUID]:
    return (left.id, right.id) if str(left.id) < str(right.id) else (right.id, left.id)


def _canonical_target(left: Location, right: Location) -> tuple[Location, Location]:
    def rank(location: Location) -> tuple:
        sources = set(location.source_codes or [])
        return (
            int("sharinet" in sources),
            len(sources),
            float(location.data_quality_score or 0),
            -location.created_at.timestamp(),
        )

    return (left, right) if rank(left) >= rank(right) else (right, left)


def _merge_missing_metadata(target: Location, duplicate: Location) -> None:
    for attribute in (
        "canonical_name_en",
        "operator_id",
        "address_id",
        "phone",
        "website_url",
        "hours_summary",
        "hours_schedule",
        "is_24_7",
        "is_public",
        "is_reservable",
    ):
        if getattr(target, attribute) in (None, "") and getattr(duplicate, attribute) not in (None, ""):
            setattr(target, attribute, getattr(duplicate, attribute))
    target.facilities = list(dict.fromkeys([*(target.facilities or []), *(duplicate.facilities or [])]))
    target.image_urls = list(dict.fromkeys([*(target.image_urls or []), *(duplicate.image_urls or [])]))
    notes = [*(target.source_notes or []), *(duplicate.source_notes or [])]
    seen: set[tuple[str, str, str]] = set()
    target.source_notes = [
        item
        for item in notes
        if isinstance(item, dict)
        and (str(item.get("source")), str(item.get("kind")), str(item.get("text"))) not in seen
        and not seen.add((str(item.get("source")), str(item.get("kind")), str(item.get("text"))))
    ]


def merge_locations(session, left: Location, right: Location) -> Location:
    """Merge two canonical locations while preserving every source record."""
    target, duplicate = _canonical_target(left, right)
    _merge_missing_metadata(target, duplicate)

    target_pools = {pool.origin_source_code: pool for pool in target.pools}
    for pool in duplicate.pools:
        existing = target_pools.get(pool.origin_source_code)
        if existing is None:
            pool.location_id = target.id
            target_pools[pool.origin_source_code] = pool
        elif pool.origin_source_code == "ocm":
            # OCM EVSEs are site-level synthetic inventories; two OCM POIs must
            # not double the physical connector count after a same-site merge.
            for evse in pool.evses:
                evse.withdrawn_at = utcnow()
        else:
            for evse in pool.evses:
                evse.pool_id = existing.id

    for observation in session.scalars(
        select(PriceObservation).where(PriceObservation.location_id == duplicate.id)
    ).all():
        observation.location_id = target.id
    for external in session.scalars(
        select(ExternalRecord).where(
            ExternalRecord.canonical_entity_type == "location",
            ExternalRecord.canonical_entity_id == duplicate.id,
        )
    ).all():
        external.canonical_entity_id = target.id

    session.flush()
    active_sources = {evse.origin_source_code for evse in iter_evses(session, target.id) if evse.withdrawn_at is None}
    if "sharinet" in active_sources and "ocm" in active_sources:
        withdraw_source_evses(session, target, "ocm", clear_notes=False)
    duplicate.deleted_at = utcnow()
    duplicate.publish_status = "withdrawn"
    recompute_source_codes(session, target)
    recompute_source_codes(session, duplicate)
    target.data_quality_score = score_location(session, target)
    return target


def _upsert_review(
    session, left: Location, right: Location, evidence: MatchEvidence
) -> DuplicateCandidate:
    left_id, right_id = _pair_ids(left, right)
    candidate = session.scalar(
        select(DuplicateCandidate).where(
            DuplicateCandidate.left_location_id == left_id,
            DuplicateCandidate.right_location_id == right_id,
        )
    )
    if candidate is None:
        candidate = DuplicateCandidate(
            left_location_id=left_id,
            right_location_id=right_id,
            status="pending",
            confidence=Decimal(str(round(evidence.confidence, 4))),
            evidence=evidence.as_dict(),
        )
        session.add(candidate)
    elif candidate.status == "pending":
        candidate.confidence = Decimal(str(round(evidence.confidence, 4)))
        candidate.evidence = evidence.as_dict()
    return candidate


def reconcile_locations(session, *, dry_run: bool = False) -> dict[str, int]:
    locations = session.scalars(
        select(Location)
        .where(Location.deleted_at.is_(None))
        .options(
            selectinload(Location.address),
            selectinload(Location.operator),
            selectinload(Location.pools).selectinload(ChargingPool.evses),
        )
    ).all()
    stats = {"scanned": len(locations), "nearby_pairs": 0, "merged": 0, "review": 0}
    for index, left in enumerate(locations):
        if left.deleted_at is not None:
            continue
        for right in locations[index + 1 :]:
            if right.deleted_at is not None:
                continue
            same_sources = bool(set(left.source_codes or []) & set(right.source_codes or []))
            assessment = assess_locations(_identity(left), _identity(right), same_source=same_sources)
            if assessment is None:
                continue
            stats["nearby_pairs"] += 1
            decision, evidence = assessment
            # ABRP locations can represent route waypoints; never auto-merge
            # same-source ABRP pairs without explicit upstream identity.
            if same_sources and set(left.source_codes or []) == {"abrp"} and set(right.source_codes or []) == {"abrp"}:
                decision = "review"
            if decision == "auto_merge":
                stats["merged"] += 1
                if not dry_run:
                    candidate = _upsert_review(session, left, right, evidence)
                    candidate.status = "merged"
                    candidate.resolved_at = utcnow()
                    merge_locations(session, left, right)
            else:
                stats["review"] += 1
                if not dry_run:
                    _upsert_review(session, left, right, evidence)
    return stats


def resolve_candidate(session, candidate_id: uuid.UUID, decision: str) -> DuplicateCandidate:
    candidate = session.get(DuplicateCandidate, candidate_id)
    if candidate is None:
        raise ValueError("duplicate candidate not found")
    if decision == "merge":
        left = session.get(Location, candidate.left_location_id)
        right = session.get(Location, candidate.right_location_id)
        if left is None or right is None:
            raise ValueError("candidate locations not found")
        if left.deleted_at is None and right.deleted_at is None:
            merge_locations(session, left, right)
        candidate.status = "merged"
    elif decision == "distinct":
        candidate.status = "not_duplicate"
    else:
        raise ValueError("decision must be merge or distinct")
    candidate.resolved_at = utcnow()
    return candidate
