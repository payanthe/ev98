from datetime import datetime
from zoneinfo import ZoneInfo

from app.domain.hours import is_open_now, parse_hours, resolve_hours
from app.ingestion.adapters.ocm import normalize_poi
from app.ingestion.adapters.sharinet import normalize_charge_point


TEHRAN = ZoneInfo("Asia/Tehran")


def _at(hour: int, minute: int = 0, *, weekday: int = 0) -> datetime:
    """Build a Tehran local time. weekday follows Python: Mon=0 … Sun=6."""
    # 2026-09-21 is a Monday.
    day = 21 + weekday
    return datetime(2026, 9, day, hour, minute, tzinfo=TEHRAN)


def test_parse_always_open_phrases():
    schedule = parse_hours("همه روزها، همه ساعات")
    assert schedule.is_24_7 is True
    assert schedule.parseable is True
    assert schedule.label == "شبانه‌روزی"
    assert is_open_now(schedule, now=_at(3)) is True


def test_parse_daily_range_with_persian_digits():
    schedule = parse_hours("همه روزها، از ۸ تا ۲۳")
    assert schedule.is_24_7 is False
    assert schedule.parseable is True
    assert schedule.label == "همه‌روزه ۸ تا ۲۳"
    assert schedule.intervals[0].start == "08:00"
    assert schedule.intervals[0].end == "23:00"
    assert is_open_now(schedule, now=_at(10)) is True
    assert is_open_now(schedule, now=_at(23)) is False
    assert is_open_now(schedule, now=_at(7, 59)) is False


def test_parse_named_weekdays():
    schedule = parse_hours("شنبه و یکشنبه از 9 تا 17")
    assert schedule.parseable is True
    assert set(schedule.intervals[0].weekdays) == {5, 6}
    assert schedule.intervals[0].start == "09:00"
    assert is_open_now(schedule, now=_at(12, weekday=5)) is True  # Saturday
    assert is_open_now(schedule, now=_at(12, weekday=0)) is False  # Monday


def test_overnight_window():
    schedule = parse_hours("همه روزها از 22 تا 6")
    assert schedule.parseable is True
    assert is_open_now(schedule, now=_at(23)) is True
    assert is_open_now(schedule, now=_at(5)) is True
    assert is_open_now(schedule, now=_at(12)) is False



def test_unparseable_hours_stay_unknown():
    schedule = parse_hours("هماهنگ با نگهبانی")
    assert schedule.parseable is False
    assert is_open_now(schedule, now=_at(12)) is None
    status = resolve_hours(hours_summary="هماهنگ با نگهبانی", now=_at(12))
    assert status.open_now is None
    assert status.open_now_label is None
    assert status.hours_label == "هماهنگ با نگهبانی"


def test_resolve_hours_open_and_closed_labels():
    open_status = resolve_hours(hours_summary="همه روزها، از 8 تا 23", now=_at(15))
    assert open_status.open_now is True
    assert open_status.open_now_label == "الان باز"
    assert open_status.hours_label == "همه‌روزه ۸ تا ۲۳"

    closed = resolve_hours(hours_summary="همه روزها، از 8 تا 23", now=_at(23, 30))
    assert closed.open_now is False
    assert closed.open_now_label == "الان بسته"


def test_sharinet_hours_become_schedule():
    record = normalize_charge_point(
        {
            "id": "MCH2",
            "stationName": "ایستگاه نمونه",
            "chargerCoordinates": {"lat": 35.7, "lon": 51.4},
            "chargerStatus": "AVAILABLE",
            "reservable": "0",
        },
        {
            "address": "تهران، مرکز",
            "workDays": "همه روزها",
            "workHours": "از 8 تا 22",
            "isFree": False,
            "power": 60,
        },
    )
    assert record is not None
    assert record.hours_summary == "همه روزها · از 8 تا 22"
    assert record.is_24_7 is False
    assert record.hours_schedule is not None
    assert record.hours_schedule["parseable"] is True
    assert record.hours_schedule["label"] == "همه‌روزه ۸ تا ۲۲"


def test_ocm_hours_schedule_from_comments():
    record = normalize_poi(
        {
            "ID": 471747,
            "UUID": "x",
            "AddressInfo": {
                "Title": "ایستگاه",
                "Latitude": 35.7,
                "Longitude": 51.4,
            },
            "Connections": [],
            "GeneralComments": "ساعات کاری همه روزها, از 8 تا 23",
            "StatusTypeID": 50,
            "UsageTypeID": 1,
            "NumberOfPoints": 1,
        }
    )
    assert record.hours_summary == "همه روزها، از 8 تا 23"
    assert record.hours_schedule is not None
    assert record.hours_schedule["label"] == "همه‌روزه ۸ تا ۲۳"
    assert record.is_24_7 is not True
