from pathlib import Path

from app.services.cars_page import CARS_URL, DESCRIPTION, TITLE, render_cars_page
from app.vehicles.catalog import load_catalog

PAGE = Path(__file__).resolve().parents[2] / "frontend" / "public" / "cars" / "index.html"


def test_cars_page_is_indexable_and_lists_every_variant():
    catalog = load_catalog()
    html = render_cars_page(catalog)

    assert html.count("<h1>") == 1
    assert "<h1>خودروهای برقی وارد شده به ایران</h1>" in html
    assert f'<link rel="canonical" href="{CARS_URL}">' in html
    assert 'content="index, follow, max-image-preview:large"' in html
    assert f"<title>{TITLE}</title>" in html
    assert "G-2EZDZLWKS1" in html
    assert DESCRIPTION in html
    assert '"@type": "FAQPage"' in html
    assert '"@type": "ItemList"' in html
    assert '"@type": "BreadcrumbList"' in html
    assert html.count("<h1") == 1
    assert 'src="/brand-icons/honda.svg"' in html
    assert 'src="/connector-icons/Type2_CCS.svg"' in html
    assert 'class="brand-fallback"' in html

    for variant in catalog.variants():
        assert f"/?vehicle={variant.id}" in html
        assert variant.display_name in html

    assert PAGE.read_text(encoding="utf-8") == html
