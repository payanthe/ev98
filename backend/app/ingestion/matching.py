"""Conservative cross-source matching for physical charging locations."""

from __future__ import annotations

import re
from dataclasses import asdict, dataclass
from difflib import SequenceMatcher

from app.domain.text import haversine_m, normalize_fa


_DIGITS = str.maketrans("۰۱۲۳۴۵۶۷۸۹٠١٢٣٤٥٦٧٨٩", "01234567890123456789")
_GENERIC_TOKENS = {
    "ایستگاه",
    "شارژ",
    "شارژر",
    "خودرو",
    "خودروی",
    "برقی",
    "مپنا",
    "شارینت",
    "station",
    "charging",
    "charger",
    "ev",
    "mapna",
    "sharinet",
}


@dataclass(frozen=True)
class LocationIdentity:
    name: str
    lat: float
    lng: float
    address: str | None = None
    operator_name: str | None = None


@dataclass(frozen=True)
class MatchEvidence:
    distance_m: float
    name_similarity: float
    address_similarity: float
    operator_match: bool
    shared_name_tokens: int
    confidence: float

    def as_dict(self) -> dict:
        data = asdict(self)
        return {
            key: round(value, 4) if isinstance(value, float) else value
            for key, value in data.items()
        }


def _tokens(value: str | None, *, drop_generic: bool = False) -> list[str]:
    normalized = normalize_fa(value).translate(_DIGITS)
    normalized = re.sub(r"[^\w\s]", " ", normalized)
    tokens = [token for token in normalized.split() if token]
    if drop_generic:
        tokens = [token for token in tokens if token not in _GENERIC_TOKENS]
    return tokens


def _similarity(left: str | None, right: str | None, *, names: bool = False) -> tuple[float, int]:
    left_tokens = _tokens(left, drop_generic=names)
    right_tokens = _tokens(right, drop_generic=names)
    if not left_tokens or not right_tokens:
        return 0.0, 0
    left_set, right_set = set(left_tokens), set(right_tokens)
    shared = len(left_set & right_set)
    jaccard = shared / len(left_set | right_set)
    containment = shared / min(len(left_set), len(right_set))
    sequence = SequenceMatcher(None, " ".join(left_tokens), " ".join(right_tokens)).ratio()
    # Containment handles source-specific suffixes; sequence handles small spelling differences.
    score = max(sequence, 0.65 * containment + 0.35 * jaccard)
    return score, shared


def _operator_family(value: str | None) -> str:
    text = normalize_fa(value).translate(_DIGITS)
    if any(token in text for token in ("مپنا", "شارینت", "mapna", "empana", "sharinet")):
        return "mapna"
    if any(token in text for token in ("ایکس ویژن", "ایکسویژن", "xvision", "xv go", "xvgo")):
        return "xvision"
    return " ".join(_tokens(text))


def match_locations(incoming: LocationIdentity, candidate: LocationIdentity) -> MatchEvidence | None:
    """Return evidence only for high-confidence automatic matches.

    Distance gates every decision. Names may differ, but a fuzzy match must retain
    at least two meaningful tokens (or an exact, sufficiently descriptive name).
    """
    distance = haversine_m(incoming.lat, incoming.lng, candidate.lat, candidate.lng)
    if distance > 250:
        return None

    name_score, shared = _similarity(incoming.name, candidate.name, names=True)
    address_score, _ = _similarity(incoming.address, candidate.address)
    incoming_operator = _operator_family(incoming.operator_name)
    candidate_operator = _operator_family(candidate.operator_name)
    operator_match = bool(incoming_operator and incoming_operator == candidate_operator)

    incoming_name = _tokens(incoming.name, drop_generic=True)
    candidate_name = _tokens(candidate.name, drop_generic=True)
    exact_name = incoming_name == candidate_name and bool(incoming_name)
    descriptive_exact = exact_name and (len(incoming_name) >= 2 or len(incoming_name[0]) >= 6)

    auto_match = (
        (distance <= 75 and descriptive_exact)
        or (distance <= 75 and shared >= 2 and name_score >= 0.68)
        or (distance <= 150 and shared >= 2 and name_score >= 0.82)
        or (distance <= 250 and shared >= 2 and name_score >= 0.94)
    )
    # A matching address/operator can rescue modest source-specific name differences,
    # but never a generic one-token station name.
    if distance <= 100 and shared >= 2 and name_score >= 0.60 and (address_score >= 0.45 or operator_match):
        auto_match = True
    # Mapna sites can have different commercial/site-owner prefixes between
    # Sharinet and catalog sources. A shared branch code plus site token is a
    # strong identity signal when the coordinates and operator family agree.
    if distance <= 50 and shared >= 2 and name_score >= 0.55 and operator_match:
        auto_match = True
    if not auto_match:
        return None

    distance_score = max(0.0, 1.0 - distance / 250.0)
    confidence = min(
        0.9999,
        0.55 * name_score
        + 0.20 * distance_score
        + 0.15 * address_score
        + (0.10 if operator_match else 0.0),
    )
    return MatchEvidence(
        distance_m=distance,
        name_similarity=name_score,
        address_similarity=address_score,
        operator_match=operator_match,
        shared_name_tokens=shared,
        confidence=confidence,
    )


def assess_locations(
    incoming: LocationIdentity, candidate: LocationIdentity, *, same_source: bool = False
) -> tuple[str, MatchEvidence] | None:
    """Classify a nearby pair as ``auto_merge`` or ``review``.

    Same-source matching is intentionally stricter: two records from one feed can
    describe separate entrances or devices at the same campus.
    """
    evidence = _match_evidence(incoming, candidate)
    if evidence is None:
        return None
    exact = _tokens(incoming.name, drop_generic=True) == _tokens(candidate.name, drop_generic=True)
    if same_source:
        automatic = (
            evidence.distance_m <= 75
            and evidence.shared_name_tokens >= 2
            and (exact or evidence.name_similarity >= 0.82)
        )
    else:
        automatic = match_locations(incoming, candidate) is not None
    return ("auto_merge" if automatic else "review", evidence)


def _match_evidence(incoming: LocationIdentity, candidate: LocationIdentity) -> MatchEvidence | None:
    distance = haversine_m(incoming.lat, incoming.lng, candidate.lat, candidate.lng)
    if distance > 250:
        return None
    name_score, shared = _similarity(incoming.name, candidate.name, names=True)
    address_score, _ = _similarity(incoming.address, candidate.address)
    incoming_operator = _operator_family(incoming.operator_name)
    candidate_operator = _operator_family(candidate.operator_name)
    operator_match = bool(incoming_operator and incoming_operator == candidate_operator)
    if shared < 2 or (name_score < 0.60 and not (distance <= 50 and name_score >= 0.55 and operator_match)):
        return None
    distance_score = max(0.0, 1.0 - distance / 250.0)
    confidence = min(
        0.9999,
        0.55 * name_score
        + 0.20 * distance_score
        + 0.15 * address_score
        + (0.10 if operator_match else 0.0),
    )
    return MatchEvidence(distance, name_score, address_score, operator_match, shared, confidence)
