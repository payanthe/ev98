"""Parse free-text opening hours and evaluate open-now in Asia/Tehran.

Sources usually give Persian phrases such as «همه روزها، از 8 تا 23».
This module turns the common cases into a small schedule JSON so the API
can return a live open/closed state without inventing hours it cannot parse.
"""

from __future__ import annotations

import re
from dataclasses import asdict, dataclass, field
from datetime import datetime
from typing import Any
from zoneinfo import ZoneInfo

from app.domain.text import normalize_fa

TEHRAN = ZoneInfo("Asia/Tehran")

_FA_DIGITS = str.maketrans("۰۱۲۳۴۵۶۷۸۹٠١٢٣٤٥٦٧٨٩", "01234567890123456789")
_TO_FA = str.maketrans("0123456789", "۰۱۲۳۴۵۶۷۸۹")

_WEEKDAY_NAMES = (
    "دوشنبه",
    "سه‌شنبه",
    "چهارشنبه",
    "پنج‌شنبه",
    "جمعه",
    "شنبه",
    "یکشنبه",
)
_DAY_ALIASES: list[tuple[str, int]] = [
    ("سه شنبه", 1),
    ("سه‌شنبه", 1),
    ("چهارشنبه", 2),
    ("پنج شنبه", 3),
    ("پنج‌شنبه", 3),
    ("پنجشنبه", 3),
    ("یکشنبه", 6),
    ("دوشنبه", 0),
    ("شنبه", 5),
    ("جمعه", 4),
]

_RANGE = re.compile(
    r"(?:از\s*)?(\d{1,2})(?::(\d{2}))?\s*(?:تا|-|–|—)\s*(\d{1,2})(?::(\d{2}))?",
)
_ALWAYS_HOURS = re.compile(r"همه\s*ساع|شبانه\s*روز|۲۴\s*ساع|24\s*ساع|24/?7|۲۴/?۷")
_ALWAYS_DAYS = re.compile(r"همه\s*روز|هر\s*روز|7\s*روز|۷\s*روز")
_CLOCK = re.compile(r"^(\d{1,2}):(\d{2})$")


@dataclass(frozen=True)
class HoursInterval:
    weekdays: tuple[int, ...]
    start: str  # HH:MM local
    end: str  # HH:MM local; may be earlier than start for overnight

    def as_dict(self) -> dict[str, Any]:
        return {"weekdays": list(self.weekdays), "start": self.start, "end": self.end}


@dataclass
class HoursSchedule:
    is_24_7: bool = False
    intervals: list[HoursInterval] = field(default_factory=list)
    label: str | None = None
    parseable: bool = False
    raw: str | None = None

    def as_dict(self) -> dict[str, Any]:
        return {
            "is_24_7": self.is_24_7,
            "intervals": [item.as_dict() for item in self.intervals],
            "label": self.label,
            "parseable": self.parseable,
            "raw": self.raw,
        }


@dataclass(frozen=True)
class HoursStatus:
    open_now: bool | None
    open_now_label: str | None
    hours_label: str | None
    hours_summary: str | None
    is_24_7: bool | None
    schedule: dict[str, Any] | None

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


def fa_digits(value: str) -> str:
    return value.translate(_TO_FA)


def parse_hours(
    summary: str | None = None,
    *,
    is_24_7: bool | None = None,
    work_days: str | None = None,
    work_hours: str | None = None,
) -> HoursSchedule:
    """Build a schedule from source text. Prefer structured day/hour parts when present."""
    parts = [part.strip() for part in (work_days, work_hours, summary) if part and str(part).strip()]
    raw = " · ".join(_unique(parts)) or None
    folded_parts = [_fold(part) for part in parts]
    folded = " ".join(folded_parts)

    if is_24_7 is True or _looks_24_7(folded, folded_parts):
        return HoursSchedule(
            is_24_7=True,
            intervals=[],
            label="شبانه‌روزی",
            parseable=True,
            raw=raw,
        )

    weekdays = _weekdays_from(folded_parts[0] if work_days else folded) if folded else ()
    if not weekdays and any(_ALWAYS_DAYS.search(part) for part in folded_parts):
        weekdays = tuple(range(7))
    if not weekdays and folded:
        # Bare time ranges with no day phrase → treat as every day.
        weekdays = tuple(range(7))

    ranges = _ranges_from(folded)
    if not ranges or not weekdays:
        label = _fallback_label(raw)
        return HoursSchedule(is_24_7=False, intervals=[], label=label, parseable=False, raw=raw)

    intervals = [HoursInterval(weekdays=weekdays, start=start, end=end) for start, end in ranges]
    label = _label_for(weekdays, ranges, is_24_7=False)
    return HoursSchedule(is_24_7=False, intervals=intervals, label=label, parseable=True, raw=raw)


def schedule_from_payload(payload: dict[str, Any] | None) -> HoursSchedule | None:
    if not isinstance(payload, dict):
        return None
    intervals: list[HoursInterval] = []
    for item in payload.get("intervals") or []:
        if not isinstance(item, dict):
            continue
        weekdays = tuple(int(day) for day in (item.get("weekdays") or []) if _valid_weekday(day))
        start = _normalize_clock(item.get("start"))
        end = _normalize_clock(item.get("end"))
        if weekdays and start and end:
            intervals.append(HoursInterval(weekdays=weekdays, start=start, end=end))
    return HoursSchedule(
        is_24_7=bool(payload.get("is_24_7")),
        intervals=intervals,
        label=str(payload["label"]) if payload.get("label") else None,
        parseable=bool(payload.get("parseable")) or bool(payload.get("is_24_7")) or bool(intervals),
        raw=str(payload["raw"]) if payload.get("raw") else None,
    )


def is_open_now(
    schedule: HoursSchedule | None,
    *,
    now: datetime | None = None,
    timezone: str = "Asia/Tehran",
) -> bool | None:
    if schedule is None or not schedule.parseable:
        return None
    if schedule.is_24_7:
        return True
    if not schedule.intervals:
        return None

    local = (now or datetime.now(TEHRAN)).astimezone(ZoneInfo(timezone) if timezone else TEHRAN)
    weekday = local.weekday()
    minute = local.hour * 60 + local.minute

    for interval in schedule.intervals:
        if weekday not in interval.weekdays:
            continue
        start = _to_minute(interval.start)
        end = _to_minute(interval.end)
        if start is None or end is None:
            continue
        if start == end:
            return True
        if start < end and start <= minute < end:
            return True
        # Overnight window, e.g. 22:00 → 06:00
        if start > end and (minute >= start or minute < end):
            return True
    return False


def resolve_hours(
    *,
    hours_summary: str | None,
    is_24_7: bool | None = None,
    hours_schedule: dict[str, Any] | None = None,
    now: datetime | None = None,
    timezone: str = "Asia/Tehran",
) -> HoursStatus:
    """Prefer stored schedule; otherwise parse the free-text summary on the fly."""
    schedule = schedule_from_payload(hours_schedule)
    if schedule is None or (not schedule.parseable and hours_summary):
        schedule = parse_hours(hours_summary, is_24_7=is_24_7)
    elif is_24_7 is True and not schedule.is_24_7:
        schedule = HoursSchedule(
            is_24_7=True,
            intervals=[],
            label="شبانه‌روزی",
            parseable=True,
            raw=schedule.raw or hours_summary,
        )

    if not schedule.raw and not schedule.label and not hours_summary and is_24_7 is not True:
        return HoursStatus(
            open_now=None,
            open_now_label=None,
            hours_label=None,
            hours_summary=None,
            is_24_7=is_24_7,
            schedule=None,
        )

    open_now = is_open_now(schedule, now=now, timezone=timezone)
    if is_24_7 is True:
        open_now = True
    open_label = None
    if open_now is True:
        open_label = "الان باز"
    elif open_now is False:
        open_label = "الان بسته"

    label = schedule.label or _fallback_label(hours_summary or schedule.raw)
    if is_24_7 is True:
        label = "شبانه‌روزی"

    return HoursStatus(
        open_now=open_now,
        open_now_label=open_label,
        hours_label=label,
        hours_summary=hours_summary or schedule.raw,
        is_24_7=True if schedule.is_24_7 or is_24_7 is True else is_24_7,
        schedule=schedule.as_dict() if schedule.parseable or schedule.raw else None,
    )


def _fold(value: str) -> str:
    text = normalize_fa(value).translate(_FA_DIGITS)
    text = text.replace("،", " ").replace(",", " ")
    return re.sub(r"\s+", " ", text).strip()


def _looks_24_7(folded: str, parts: list[str]) -> bool:
    if not folded:
        return False
    if _ALWAYS_HOURS.search(folded) and (_ALWAYS_DAYS.search(folded) or not any(_day_tokens(part) for part in parts)):
        return True
    if "24/7" in folded or "۲۴/۷" in folded.replace(" ", ""):
        return True
    has_all_days = any(_ALWAYS_DAYS.search(part) for part in parts)
    has_all_hours = any(_ALWAYS_HOURS.search(part) for part in parts)
    return has_all_days and has_all_hours


def _weekdays_from(text: str) -> tuple[int, ...]:
    if not text:
        return ()
    if _ALWAYS_DAYS.search(text):
        return tuple(range(7))
    found = _day_tokens(text)
    return tuple(sorted(set(found)))


def _day_tokens(text: str) -> list[int]:
    found: list[int] = []
    remaining = text
    for alias, day in sorted(_DAY_ALIASES, key=lambda item: -len(item[0])):
        if alias in remaining:
            found.append(day)
            remaining = remaining.replace(alias, " ")
    return found


def _ranges_from(text: str) -> list[tuple[str, str]]:
    ranges: list[tuple[str, str]] = []
    for match in _RANGE.finditer(text):
        start_h, start_m, end_h, end_m = match.groups()
        start = _clock(int(start_h), int(start_m or 0))
        end = _clock(int(end_h), int(end_m or 0))
        if start and end:
            ranges.append((start, end))
    return _unique_pairs(ranges)


def _clock(hour: int, minute: int) -> str | None:
    if hour == 24 and minute == 0:
        return "24:00"
    if not (0 <= hour <= 23 and 0 <= minute <= 59):
        return None
    return f"{hour:02d}:{minute:02d}"


def _normalize_clock(value: object) -> str | None:
    if not isinstance(value, str):
        return None
    text = value.translate(_FA_DIGITS).strip()
    match = _CLOCK.fullmatch(text)
    if not match:
        return None
    return _clock(int(match.group(1)), int(match.group(2)))


def _to_minute(value: str) -> int | None:
    if value == "24:00":
        return 24 * 60
    match = _CLOCK.fullmatch(value)
    if not match:
        return None
    return int(match.group(1)) * 60 + int(match.group(2))


def _valid_weekday(value: object) -> bool:
    try:
        return 0 <= int(value) <= 6
    except (TypeError, ValueError):
        return False


def _label_for(weekdays: tuple[int, ...], ranges: list[tuple[str, str]], *, is_24_7: bool) -> str:
    if is_24_7:
        return "شبانه‌روزی"
    day_part = "همه‌روزه" if set(weekdays) == set(range(7)) else "، ".join(_WEEKDAY_NAMES[day] for day in weekdays)
    time_part = " و ".join(f"{fa_digits(_pretty(start))} تا {fa_digits(_pretty(end))}" for start, end in ranges)
    if day_part and time_part:
        return f"{day_part} {time_part}"
    return day_part or time_part or ""


def _pretty(clock: str) -> str:
    if clock.endswith(":00"):
        return str(int(clock.split(":", 1)[0]))
    return clock.lstrip("0") if not clock.startswith("0:") else clock


def _fallback_label(raw: str | None) -> str | None:
    if not raw:
        return None
    cleaned = re.sub(r"\s+", " ", raw).strip(" ·،,")
    return cleaned or None


def _unique(values: list[str]) -> list[str]:
    seen: set[str] = set()
    out: list[str] = []
    for value in values:
        key = _fold(value)
        if not key or key in seen:
            continue
        seen.add(key)
        out.append(value.strip())
    return out


def _unique_pairs(values: list[tuple[str, str]]) -> list[tuple[str, str]]:
    seen: set[tuple[str, str]] = set()
    out: list[tuple[str, str]] = []
    for item in values:
        if item in seen:
            continue
        seen.add(item)
        out.append(item)
    return out
