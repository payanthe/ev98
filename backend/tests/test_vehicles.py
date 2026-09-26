from app.vehicles.catalog import get_catalog, load_catalog


def _by_external(external_id: str):
    catalog = load_catalog()
    for variant in catalog.variants():
        if variant.source_external_id == external_id:
            return variant
    raise AssertionError(external_id)


def test_catalog_normalizes_makes_connectors_and_stable_ids():
    catalog = load_catalog()
    variants = catalog.variants()
    assert len(variants) == 44
    assert len({item.id for item in variants}) == 44
    assert load_catalog().variants()[0].id == variants[0].id

    crozz = _by_external("6a13d1305e826116505d173f")
    assert crozz.display_name == "فولکس‌واگن ID.4 Crozz"
    assert crozz.station_standards == ("GBT_DC", "GBT_AC")
    assert crozz.verification_status == "needs_review"
    assert any("واردکننده" in warning for warning in crozz.warnings)

    ix1 = _by_external("6a13d1305e826116505d1751")
    assert ix1.display_name == "ب‌ام‌و iX1"
    assert ix1.ac_charge_limit_kw == 22
    assert ix1.battery_kwh_min == 64.7

    outlander = _by_external("6a13d1305e826116505d174d")
    assert outlander.station_standards == ("CHADEMO", "TYPE_1")

    hongqi = _by_external("6a13d1305e826116505d174e")
    assert hongqi.display_name.startswith("هونگچی")
    assert hongqi.dc_charge_limit_kw == 48
    assert hongqi.ac_charge_limit_kw is None


def test_swapped_brand_and_model_columns_are_corrected():
    g6 = _by_external("6a13d1305e826116505d1766")
    assert g6.display_name == "اکس‌پنگ G6"
    assert g6.model_name == "G6"

    aion = _by_external("6a13d1305e826116505d1764")
    assert aion.display_name == "گک Aion V Plus"

    roewe = _by_external("6a13d1305e826116505d1763")
    assert roewe.display_name == "رووی ERX5"
    assert roewe.no_dc_declared is True
    assert roewe.station_standards == ("GBT_AC",)


def test_same_model_keeps_distinct_variants_when_connectors_differ():
    older = _by_external("6a13d1305e826116505d1752")
    newer = _by_external("6a13d1305e826116505d1761")
    assert older.model_year == 2023
    assert newer.model_year == 2025
    assert older.model_name == newer.model_name == "Free"
    assert older.station_standards == ("GBT_DC", "GBT_AC")
    assert newer.station_standards == ("CCS_2", "TYPE_2")
    assert older.id != newer.id


def test_search_blob_matches_persian_and_english_aliases():
    catalog = get_catalog()
    blobs = [variant.search for variant in catalog.variants()]
    assert any("بنز" in blob or "مرسدسبنز" in blob for blob in blobs)
    assert any("بیامو" in blob for blob in blobs)
    assert any("تویوتا" in blob for blob in blobs)
    assert any("bz3x" in blob or "bz4x" in blob for blob in blobs)

    toyota = [variant for variant in catalog.variants() if "تویوتا" in variant.display_name]
    assert {variant.model_name for variant in toyota} == {"bZ3X", "bZ4X"}
