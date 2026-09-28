import json
import re
import uuid
from datetime import UTC, datetime
from pathlib import Path

from app.schemas.api import LocationDetail
from app.services.station_page import render_station_page


def _location() -> LocationDetail:
    return LocationDetail(
        id=uuid.uuid4(),
        slug="تهران-ونک",
        name="ایستگاه شارژ ونک",
        city="تهران",
        province="تهران",
        lat=35.757,
        lng=51.41,
        facilities=[],
        notes=[],
        images=[],
        availability="operational",
        availability_label="عملیاتی",
        is_stale=False,
        max_power_kw=60,
        source_codes=["ocm"],
        sources=[],
        evses=[],
        field_provenance={},
        updated_at=datetime(2026, 9, 28, tzinfo=UTC),
    )


def test_station_html_has_server_rendered_metadata_and_valid_schema(tmp_path: Path):
    source = Path(__file__).resolve().parents[2] / "frontend" / "dist" / "index.html"
    index = tmp_path / "index.html"
    index.write_text(source.read_text(encoding="utf-8"), encoding="utf-8")

    html = render_station_page(str(index), "https://ev98.ir", _location(), "تهران-ونک")

    assert "<title>ایستگاه شارژ ونک در تهران | EV98</title>" in html
    assert '<link rel="canonical" href="https://ev98.ir/stations/تهران-ونک">' in html
    assert 'content="index, follow, max-image-preview:large"' in html
    match = re.search(r'<script id="station-jsonld" type="application/ld\+json">(.*?)</script>', html)
    assert match is not None
    schema = json.loads(match.group(1))
    assert schema["@graph"][1]["geo"]["latitude"] == 35.757


def test_missing_station_is_noindex(tmp_path: Path):
    index = tmp_path / "index.html"
    index.write_text('<html><head><title>Home</title><meta name="robots" content="index"></head></html>', encoding="utf-8")

    html = render_station_page(str(index), "https://ev98.ir", None, "missing")

    assert "<title>ایستگاه پیدا نشد | EV98</title>" in html
    assert 'content="noindex, follow"' in html


def test_station_summary_does_not_publish_unknown_operator():
    location = _location().model_copy(update={"operator_name": "(Unknown Operator)"})

    html = render_station_page(
        str(Path(__file__).resolve().parents[2] / "frontend" / "dist" / "index.html"),
        "https://ev98.ir",
        location,
        location.slug,
    )

    assert "Unknown Operator" not in re.search(r'<meta name="description" content="(.*?)">', html).group(1)
