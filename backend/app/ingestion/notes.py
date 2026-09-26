"""Turn free-text source comments into location notes.

Hours and facilities stay on their own fields. Prices, brand labels,
connector inventories, and personal opinions never become a note.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime

from app.domain.text import normalize_fa
from app.ingestion.records import NormalizedNote

_NOTICE_TYPES = {50, 1000}
_FORM_MARKERS = ("telephone number", "access comments", "related website", "previous", "submit")
_CONSTRAINT = re.compile(
    r"اولویت|ممنوع|فقط|پیک|تاکسی|شخصی|همزمان|only one|one car|هزینه|محدود|بسته|کد|تماس|رزرو|نوبت|کارت|اشتراک|خراب",
    re.IGNORECASE,
)
_OPINION = re.compile(r"عالی|خیلی\s*خوب|awesome|excellent", re.IGNORECASE)
_ONLY_ONE = re.compile(r"only one car", re.IGNORECASE)
_HOURS = re.compile(r"ساعات?\s+کاری?")
_CONNECTOR_TOKEN = re.compile(r"^(?:\d+|gbt|gb|t|ccs2?|type2|type|chademo|dc|ac)$", re.IGNORECASE)
_FACILITY_RULES = (
    ("سرویس بهداشتی", "سرویس بهداشتی"),
    ("بهداشت", "سرویس بهداشتی"),
    ("چای رایگان", "چای رایگان"),
    ("کارواش", "کارواش"),
    ("کافه", "کافه"),
    ("نمازخانه", "نمازخانه"),
    ("رستوران", "رستوران"),
    ("مزرعه کودک", "مزرعه کودک"),
    ("مزرعه", "مزرعه کودک"),
    ("بازار مبل", "بازار مبل"),
    ("مرکز خرید", "مرکز خرید"),
    ("هتل", "هتل"),
    ("فضای سرپوشیده", "فضای سرپوشیده"),
    ("سرپوشیده", "فضای سرپوشیده"),
    ("پارکینگ رایگان", "پارکینگ رایگان"),
    ("پارکینگ", "پارکینگ"),
)


@dataclass
class SourceAnnotations:
    notes: list[NormalizedNote]
    hours_summary: str | None = None
    is_24_7: bool | None = None
    facilities: list[str] | None = None

    def __post_init__(self) -> None:
        if self.facilities is None:
            self.facilities = []


def extract_ocm_annotations(poi: dict) -> SourceAnnotations:
    notes: list[NormalizedNote] = []
    hours: list[str] = []
    facilities: list[str] = []
    address = poi.get("AddressInfo") if isinstance(poi.get("AddressInfo"), dict) else {}
    blobs = [
        _clean(poi.get("GeneralComments")),
        _clean(address.get("AccessComments")),
    ]
    for connection in poi.get("Connections") or []:
        if isinstance(connection, dict):
            blobs.append(_clean(connection.get("Comments")))

    for blob in blobs:
        if not blob or _junk(blob):
            continue
        for segment in _segments(blob):
            if _junk(segment) or _is_hours(segment):
                phrase = _hours_phrase(segment) if _is_hours(segment) else None
                if phrase:
                    hours.append(phrase)
                continue
            found = _facilities_in(segment)
            if found and not _constraint(segment):
                facilities.extend(found)
                continue
            note = _access_note(segment)
            if note:
                notes.append(NormalizedNote(text=note, kind="access"))

    notes.extend(_user_notices(poi))
    unique_hours = _unique(hours)
    always_open = any(_always_open(phrase) for phrase in unique_hours) or None
    return SourceAnnotations(
        notes=_unique_notes(notes),
        hours_summary=" · ".join(unique_hours) or None,
        is_24_7=True if always_open else None,
        facilities=_unique(facilities),
    )


def _clean(value: object) -> str:
    if not isinstance(value, str):
        return ""
    return " ".join(value.split())


def _fold(value: str) -> str:
    return normalize_fa(value.replace("ى", "ی").replace("ي", "ی"))


def _junk(text: str) -> bool:
    folded = text.casefold()
    if "undefined" in folded:
        return True
    return sum(marker in folded for marker in _FORM_MARKERS) >= 2


def _constraint(text: str) -> bool:
    return _CONSTRAINT.search(text) is not None


def _segments(text: str) -> list[str]:
    pieces = re.split(r"(?<=[.!?؟])\s+|؛", text)
    segments: list[str] = []
    for piece in pieces:
        for bit in re.split(r"(?=ساعات?\s*کاری?)", piece):
            segment = bit.strip(" ،.")
            if segment:
                segments.append(segment)
    return segments


def _is_hours(text: str) -> bool:
    return _HOURS.search(text) is not None


def _hours_phrase(text: str) -> str:
    phrase = _HOURS.sub("", text, count=1).strip(" ،.")
    phrase = phrase.replace(",", "،")
    return " ".join(phrase.split())


def _always_open(phrase: str) -> bool:
    folded = _fold(phrase)
    return "همه ساع" in folded and "همه روز" in folded


def _facilities_in(text: str) -> list[str]:
    if "free parking" in text.casefold():
        return ["پارکینگ رایگان"]
    folded = _fold(text)
    candidates: list[tuple[int, int, str, int]] = []
    for needle, label in _FACILITY_RULES:
        token = _fold(needle)
        index = folded.find(token) if token else -1
        if index >= 0:
            candidates.append((index, -len(token), label, index + len(token)))
    found: list[str] = []
    spans: list[tuple[int, int]] = []
    for index, _length, label, end in sorted(candidates):
        if any(index < stop and end > start for start, stop in spans):
            continue
        if label in found:
            continue
        found.append(label)
        spans.append((index, end))
    return found


def _connector_inventory(text: str) -> bool:
    spaced = re.sub(r"(?<=\d)(?=[A-Za-z])|(?<=[A-Za-z])(?=\d)", " ", text)
    tokens = [token for token in re.split(r"[\s/+-]+", spaced) if token]
    return bool(tokens) and all(_CONNECTOR_TOKEN.fullmatch(token) for token in tokens)


def _is_short_label(text: str) -> bool:
    if _constraint(text):
        return False
    return len(text) <= 24 and len(text.split()) <= 3


def _access_note(text: str) -> str | None:
    if _connector_inventory(text):
        return None
    if _OPINION.search(text) and not _constraint(text):
        return None
    if _ONLY_ONE.search(text):
        return "فقط یک خودرو همزمان می‌تواند شارژ شود"
    if _is_short_label(text):
        return None
    return text or None


def _user_notices(poi: dict) -> list[NormalizedNote]:
    notes: list[NormalizedNote] = []
    for item in poi.get("UserComments") or []:
        if not isinstance(item, dict):
            continue
        try:
            type_id = int(item.get("CommentTypeID"))
        except (TypeError, ValueError):
            continue
        if type_id not in _NOTICE_TYPES:
            continue
        text = _clean(item.get("Comment"))
        if not text or _junk(text) or _connector_inventory(text):
            continue
        if _OPINION.search(text) and not _constraint(text):
            continue
        notes.append(NormalizedNote(text=text, kind="notice", observed_at=_parse_time(item.get("DateCreated"))))
    return notes


def _parse_time(value: object) -> datetime | None:
    if not isinstance(value, str) or not value.strip():
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None


def _unique(values: list[str]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for value in values:
        key = _fold(value)
        if not key or key in seen:
            continue
        seen.add(key)
        result.append(value)
    return result


def _unique_notes(notes: list[NormalizedNote]) -> list[NormalizedNote]:
    seen: set[str] = set()
    result: list[NormalizedNote] = []
    for note in notes:
        key = _fold(note.text)
        if not key or key in seen:
            continue
        seen.add(key)
        result.append(note)
    return result
