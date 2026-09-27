from datetime import UTC, datetime, timedelta

from app.domain.priority import claim
from app.domain.status import AVAILABLE, CHARGING, UNAVAILABLE, summarize_statuses
from app.domain.text import haversine_m, normalize_fa, toman_to_rial
from app.ingestion.adapters.abrp import normalize_charger, parse_ocm_id
from app.ingestion.adapters.ocm import normalize_poi
from app.ingestion.adapters.sharinet import normalize_charge_point
from app.ingestion.cluster import cluster_charge_points
from app.ingestion.matching import LocationIdentity, assess_locations, match_locations
from app.ingestion.persist import operator_slug, replace_source_notes
from app.ingestion.records import NormalizedNote, NormalizedRecord
from app.models.entities import Location


def _point(name: str, lat: float, lng: float, external_id: str) -> NormalizedRecord:
    return NormalizedRecord(
        source_code="sharinet",
        entity_type="charge_point",
        external_id=external_id,
        name=name,
        lat=lat,
        lng=lng,
    )


def test_persian_normalization_and_cluster_key():
    assert normalize_fa("ايستگاه شارژ  كرمان") == normalize_fa("ایستگاه شارژ کرمان")
    assert normalize_fa("ایستگاه شارژ پارکینگ طالقانی", cluster_key=True) == normalize_fa(
        "پارکینگ طالقانی", cluster_key=True
    )


def test_same_name_nearby_chargers_become_one_location():
    records = [
        _point("ایستگاه شارژ پارکینگ طالقانی", 35.7000, 51.4000, "a"),
        _point("ایستگاه شارژ پارکینگ طالقانی", 35.7004, 51.4002, "b"),
        _point("ایستگاه شارژ پارکینگ طالقانی", 36.2000, 52.2000, "c"),
        _point("ایستگاه دیگر", 35.7001, 51.4001, "d"),
    ]
    groups = cluster_charge_points(records, max_distance_m=250)
    sizes = sorted(len(group) for group in groups)
    assert sizes == [1, 1, 2]
    assert haversine_m(35.7, 51.4, 36.2, 52.2) > 250


def test_cross_source_match_accepts_source_specific_name_variations():
    sharinet = LocationIdentity(
        name="ایستگاه شارژ شهرداری منطقه ۹",
        lat=35.6997079,
        lng=51.3468714,
        address="خیابان آزادی، استاد معین، شهرداری منطقه ۹",
        operator_name="شارینت",
    )
    ocm = LocationIdentity(
        name="شارژر خودرو برقی شهرداری منطقه 9 - مپنا",
        lat=35.699653,
        lng=51.3463833,
        address="کنارگذر آزادی",
        operator_name="مپنا - eMapna (IR)",
    )
    evidence = match_locations(sharinet, ocm)
    assert evidence is not None
    assert 40 < evidence.distance_m < 50
    assert evidence.shared_name_tokens == 3
    assert evidence.operator_match is True


def test_cross_source_match_accepts_mapna_branch_code_with_different_site_owner_prefixes():
    sharinet = LocationIdentity(
        name="ایستگاه شارژ نبکا 2403 رضایی",
        lat=36.3921436,
        lng=54.9448679,
        address="شاهرود، میدان هفتم تیر، ابتدای جاده کارخانه قند، جنب مجتمع خودروئی رضائی",
        operator_name="شارینت",
    )
    ocm = LocationIdentity(
        name="ایستگاه شارژ کرمان موتور نمایندگی 2403 رضایی",
        lat=36.3923967,
        lng=54.9447153,
        address="شاهرود",
        operator_name="مپنا - empana (IR)",
    )
    decision = assess_locations(sharinet, ocm)
    assert decision is not None
    assert decision[0] == "auto_merge"
    assert decision[1].operator_match is True


def test_sharinet_records_attribute_mapna_as_network_operator():
    record = normalize_charge_point(
        {
            "id": "MCH-OPERATOR",
            "stationName": "ایستگاه شارژ نمونه",
            "chargerCoordinates": {"lat": 35.7, "lon": 51.4},
        },
        None,
    )
    assert record is not None
    assert record.source_code == "sharinet"
    assert record.operator_name == "مپنا"


def test_operator_slug_canonicalizes_known_network_aliases():
    assert operator_slug("مپنا - eMapna (IR)") == "mapna"
    assert operator_slug("ایکس ویژن - XV Go (IR)") == "xvision"
    assert operator_slug("XV Go") == "xvision"


def test_cross_source_match_rejects_nearby_generic_or_different_names():
    generic = LocationIdentity(name="ایستگاه شارژ", lat=35.7, lng=51.4)
    another_generic = LocationIdentity(name="شارژر خودرو برقی", lat=35.7001, lng=51.4001)
    assert match_locations(generic, another_generic) is None

    first = LocationIdentity(name="پارکینگ طالقانی", lat=35.7, lng=51.4)
    second = LocationIdentity(name="مرکز خرید کوروش", lat=35.7001, lng=51.4001)
    assert match_locations(first, second) is None


def test_cross_source_match_rejects_same_name_beyond_site_radius():
    first = LocationIdentity(name="شهرداری منطقه ۹", lat=35.7, lng=51.4)
    second = LocationIdentity(name="شهرداری منطقه 9", lat=35.704, lng=51.4)
    assert match_locations(first, second) is None


def test_same_source_reconciliation_is_stricter_and_routes_borderline_pairs_to_review():
    close = LocationIdentity(name="ایستگاه شارژ میلاد نور", lat=32.7103, lng=51.7644)
    close_variant = LocationIdentity(name="ایستگاه شارژ نبکا میلاد نور", lat=32.7107, lng=51.7642)
    decision = assess_locations(close, close_variant, same_source=True)
    assert decision is not None
    assert decision[0] == "auto_merge"

    far = LocationIdentity(name="ایستگاه شارژ پارکینگ چمران", lat=32.6938881, lng=51.6782905)
    far_duplicate = LocationIdentity(name="ایستگاه شارژ پارکینگ چمران", lat=32.6937158, lng=51.6764284)
    decision = assess_locations(far, far_duplicate, same_source=True)
    assert decision is not None
    assert decision[0] == "review"


def test_sharinet_prefers_free_connector_over_charger_status():
    record = normalize_charge_point(
        {
            "id": "MCH1",
            "stationName": "ایستگاه شارژ نمونه",
            "chargerCoordinates": {"lat": 35.7, "lon": 51.4},
            "chargerStatus": "Unavailable",
            "reservable": "0",
            "connectorsCount": {"total": 2, "available": 1, "unavailable": 1, "charging": 0},
        },
        {
            "name": "ایستگاه شارژ نمونه",
            "address": "تهران، ونک، خیابان نمونه",
            "power": "60",
            "workDays": "همه روزها",
            "workHours": "همه ساعات",
            "facilities": "کافه، پارکینگ",
            "isFree": False,
            "currencyUnit": "تومان",
            "plan": {"cost": 1971, "timeTypeLable": "کم‌باری", "time": "2026-09-26T09:00:00+03:30"},
            "connectors": [
                {"id": 1, "connectorType": "DC", "connectorName": "Car-DC-CCS2", "status": "در دسترس", "statusCode": 1, "power": "60"},
                {"id": 2, "connectorType": "DC", "connectorName": "Car-DC-GB/T", "status": "خارج از دسترس", "statusCode": 3, "power": "60"},
            ],
            "images": [{"data_url": "https://example.com/station.jpg"}],
        },
    )
    assert record is not None
    evse = record.evses[0]
    assert evse.status == AVAILABLE
    assert evse.reported_status == UNAVAILABLE
    assert [item.standard for item in evse.connectors] == ["CCS_2", "GBT_DC"]
    assert record.price_toman_per_kwh == 1971
    assert toman_to_rial(1971) == 19710
    assert record.is_24_7 is True
    assert record.city == "ونک"
    assert record.facilities == ["کافه", "پارکینگ"]


def test_ocm_keeps_connections_on_one_evse_and_hides_removed():
    published = normalize_poi(
        {
            "ID": 478465,
            "StatusTypeID": 50,
            "SubmissionStatusTypeID": 200,
            "UsageTypeID": 1,
            "NumberOfPoints": 2,
            "OperatorInfo": {"Title": "شبکه نمونه"},
            "AddressInfo": {
                "Title": "دپارتمان استور روشا",
                "AddressLine1": "تهران",
                "Town": "تهران",
                "Latitude": 35.8,
                "Longitude": 51.44,
                "ContactTelephone1": "021000",
            },
            "Connections": [
                {"ConnectionTypeID": 33, "PowerKW": 50, "Quantity": 1, "CurrentTypeID": 30},
                {"ConnectionTypeID": 25, "PowerKW": 22, "Quantity": 2, "CurrentTypeID": 20},
            ],
        }
    )
    assert published is not None
    assert published.publish is True
    assert len(published.evses) == 1
    assert [item.standard for item in published.evses[0].connectors] == ["CCS_2", "TYPE_2", "TYPE_2"]
    assert published.is_public is True
    removed = normalize_poi(
        {
            "ID": 9,
            "StatusTypeID": 200,
            "AddressInfo": {"Title": "برچیده", "Latitude": 35, "Longitude": 51},
        }
    )
    assert removed is not None
    assert removed.publish is False


def test_ocm_imports_enabled_photos_only():
    record = _ocm(
        477301,
        MediaItems=[
            {"ItemURL": "https://media.openchargemap.io/photo.jpg", "IsEnabled": True, "IsVideo": False},
            {"ItemURL": "https://media.openchargemap.io/photo.jpg", "IsEnabled": True, "IsVideo": False},
            {"ItemURL": "https://media.openchargemap.io/disabled.jpg", "IsEnabled": False},
            {"ItemURL": "https://media.openchargemap.io/video.mp4", "IsVideo": True},
            {"ItemURL": "http://media.openchargemap.io/insecure.jpg", "IsEnabled": True},
        ],
    )

    assert record.image_urls == ["https://media.openchargemap.io/photo.jpg"]


def test_abrp_ocm_link_parses_explicit_source():
    payload = {
        "id": 435643484,
        "name": "ایستگاه شارژ دپارتمان استور روشا",
        "address": "تهران",
        "coordinates": {"lat": 35.8078, "long": 51.4463},
        "source": "ocm",
        "editableUrl": "https://openchargemap.org/site/poi/edit/478465",
        "hasDynamicStatus": False,
        "network": {"id": 1, "name": "شبکه"},
        "accessibility": {"status": "OPEN"},
        "evses": [{"id": "478465*1", "connectors": [{"standard": "TYPE2", "power": 11000}]}],
    }
    assert parse_ocm_id(payload) == "478465"
    record = normalize_charger(payload)
    assert record is not None
    assert record.ocm_external_id == "478465"
    assert record.evses[0].connectors[0].standard == "TYPE_2"
    assert record.evses[0].connectors[0].max_power_w == 11000
    assert record.has_dynamic_status is False


def _ocm(poi_id: int, **extra) -> NormalizedRecord:
    poi = {
        "ID": poi_id,
        "StatusTypeID": 50,
        "SubmissionStatusTypeID": 200,
        "UsageTypeID": 1,
        "AddressInfo": {"Title": "ایستگاه", "Latitude": 35.7, "Longitude": 51.4},
        "Connections": [],
    }
    poi.update(extra)
    record = normalize_poi(poi)
    assert record is not None
    return record


def test_ocm_keeps_access_notes_and_ignores_raw_prices():
    record = _ocm(
        505295,
        GeneralComments="اولویت تاکسی در زمان غیر پیک امکان شارژ خودروهای شخصی وجد دارد",
        UsageCost="525",
    )
    assert [note.text for note in record.notes] == [
        "اولویت تاکسی در زمان غیر پیک امکان شارژ خودروهای شخصی وجد دارد"
    ]
    assert record.price_toman_per_kwh is None
    assert record.is_free is False

    priced = _ocm(507088, UsageCost="200000IRT/h")
    assert priced.notes == []
    assert priced.price_toman_per_kwh is None
    assert priced.is_free is False


def test_ocm_routes_hours_and_facilities_out_of_notes():
    mixed = _ocm(
        471747,
        GeneralComments="امکانات رفاهی کارواش، کافه، سرویس بهداشتی، نمازخانه، رستوران، مزرعه کودک، هتل، بازار مبل، مرکز خرید. ساعات کاری همه روزها, از 8 تا 23",
        Connections=[{"Comments": "کارواش، کافه، سرویس بهداشتی، نمازخانه، رستوران، مزرعه کودک، هتل، بازار مبل، مرکز خرید."}],
    )
    assert mixed.notes == []
    assert mixed.hours_summary == "همه روزها، از 8 تا 23"
    assert mixed.is_24_7 is None
    assert mixed.facilities == ["کارواش", "کافه", "سرویس بهداشتی", "نمازخانه", "رستوران", "مزرعه کودک", "هتل", "بازار مبل", "مرکز خرید"]

    always = _ocm(471746, Connections=[{"Comments": "ساعات کاری همه روزها, همه ساعات"}])
    assert always.notes == []
    assert always.hours_summary == "همه روزها، همه ساعات"
    assert always.is_24_7 is True


def test_ocm_drops_junk_comments_and_keeps_real_constraints():
    assert _ocm(489486, GeneralComments="XVision").notes == []
    assert _ocm(489477, GeneralComments="نفت ابزار").notes == []
    assert _ocm(471013, GeneralComments="undefined undefined https://www.google.com/maps/search/?api=1&query=undefined").notes == []
    scraped = _ocm(
        471748,
        GeneralComments="امکانات رفاهی هتل، سرویس بهداشتی ساعات کاری همه روزها Main Telephone Number Other Telephone Number Access CommentsRelated Website Previous Submit",
    )
    assert scraped.notes == []
    assert scraped.facilities == []

    parking = _ocm(508476, GeneralComments="پارکینگ هزینه دارد")
    assert [note.text for note in parking.notes] == ["پارکینگ هزینه دارد"]
    assert parking.facilities == []

    platinum = _ocm(
        478225,
        GeneralComments="فقط بزای خودروهای شخصی- تاکسی و خودروهای عمومی ممنوع",
        AddressInfo={
            "Title": "ایستگاه",
            "Latitude": 35.7,
            "Longitude": 51.4,
            "AccessComments": "سرويس مجزا بهداشتى ، اب چاي رايگان ، محيط سرپوشيده",
        },
    )
    assert [note.text for note in platinum.notes] == ["فقط بزای خودروهای شخصی- تاکسی و خودروهای عمومی ممنوع"]
    assert platinum.facilities == ["سرویس بهداشتی", "چای رایگان", "فضای سرپوشیده"]

    opinion = _ocm(478331, AddressInfo={"Title": "ایستگاه", "Latitude": 35.7, "Longitude": 51.4, "AccessComments": "بسیار بسیار عالی هم از نظر سرعت و هم از لحاظ موقعیت"})
    assert opinion.notes == []

    inventory = _ocm(470966, GeneralComments="2gbt - 2 ccs2", AddressInfo={"Title": "ایستگاه", "Latitude": 35.7, "Longitude": 51.4, "AccessComments": "Free Parking"})
    assert inventory.notes == []
    assert inventory.facilities == ["پارکینگ رایگان"]

    shared = _ocm(4783311, Connections=[{"Comments": "دو خودرو همزمان هرکدام ۶۰ کیلو وات"}])
    assert [note.text for note in shared.notes] == ["دو خودرو همزمان هرکدام ۶۰ کیلو وات"]

    one_car = _ocm(
        472761,
        Connections=[
            {"Comments": "ONLY ONE CAR IS POSSIBLE TO CHARGE"},
            {"Comments": "ONLY ONE CAR"},
        ],
    )
    assert [note.text for note in one_car.notes] == ["فقط یک خودرو همزمان می‌تواند شارژ شود"]
    assert _ocm(471014, Connections=[{"Comments": "GB/T DC"}]).notes == []


def test_ocm_user_notice_stays_separate_from_access_notes():
    record = _ocm(
        478228,
        UserComments=[
            {
                "CommentTypeID": 50,
                "Comment": "شارژ روی ۹۰٪ محدود شده",
                "DateCreated": "2026-09-25T09:33:19.227Z",
                "Rating": 4,
            },
            {"CommentTypeID": 10, "Comment": "جای خوبی بود", "DateCreated": "2026-09-25T09:33:19.227Z"},
        ],
    )
    assert [(note.kind, note.text) for note in record.notes] == [("notice", "شارژ روی ۹۰٪ محدود شده")]
    assert record.notes[0].observed_at is not None


def test_source_notes_from_one_source_do_not_erase_another():
    location = Location(
        canonical_name_fa="نمونه",
        slug="note-test",
        latitude=35,
        longitude=51,
        source_notes=[{"source": "sharinet", "kind": "access", "text": "از شارینت", "observed_at": None}],
    )
    replace_source_notes(location, "ocm", [NormalizedNote(text="اولویت با تاکسی", kind="access")])
    assert [item["source"] for item in location.source_notes] == ["sharinet", "ocm"]
    replace_source_notes(location, "ocm", [])
    assert location.source_notes == [{"source": "sharinet", "kind": "access", "text": "از شارینت", "observed_at": None}]


def test_field_priority_keeps_stronger_coordinates():
    provenance: dict = {}
    assert claim(provenance, "coordinates", "sharinet") is True
    assert claim(provenance, "coordinates", "ocm") is False
    assert claim(provenance, "canonical_name_fa", "sharinet") is True
    assert claim(provenance, "canonical_name_fa", "ocm") is True


def test_expired_live_status_is_not_available():
    now = datetime.now(UTC)
    state, stale = summarize_statuses(
        [("AVAILABLE", "live", now - timedelta(minutes=1), None)],
        now,
    )
    assert state == "stale"
    assert stale is True
    fresh, fresh_stale = summarize_statuses(
        [("AVAILABLE", "live", now + timedelta(minutes=5), None), ("CHARGING", "live", now + timedelta(minutes=5), None)],
        now,
    )
    assert fresh == "available"
    assert fresh_stale is False
    assert CHARGING
