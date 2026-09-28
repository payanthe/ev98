"""Static, indexable catalog page for imported EVs in Iran.

The map app is a client-rendered shell. This page is plain HTML so Google
can read the catalog, the canonical URL, and the structured data without
executing the application bundle.
"""

from __future__ import annotations

import json
import re
from datetime import date
from html import escape

from app.vehicles.catalog import VehicleCatalog, VehicleVariant

SITE = "https://ev98.ir"
CARS_PATH = "/cars/"
CARS_URL = f"{SITE}{CARS_PATH}"
CARS_UPDATED = date(2026, 9, 28)

TITLE = "خودروهای برقی وارداتی ایران | EV98"
DESCRIPTION = (
    "فهرست خودروهای برقی و پلاگین‌هیبرید واردشده به ایران با واردکننده، "
    "باتری، برد و سوکت شارژ. شارژر سازگار هر مدل را روی نقشه EV98 پیدا کنید."
)

_DIGIT = str.maketrans("0123456789.", "۰۱۲۳۴۵۶۷۸۹٫")
_SEARCH = str.maketrans(
    {
        "ي": "ی",
        "ى": "ی",
        "ئ": "ی",
        "ك": "ک",
        "أ": "ا",
        "إ": "ا",
        "آ": "ا",
        "ة": "ه",
        "ؤ": "و",
        "\u200c": "",
    }
)

FUEL_TYPE = {
    "BEV": "Electric",
    "PHEV": "Hybrid electric / gasoline",
    "EREV": "Electric with range extender",
    "HEV": "Hybrid electric",
}

POWER_FILTERS = (
    ("all", "همه"),
    ("BEV", "برقی"),
    ("PHEV", "پلاگین‌هیبرید"),
    ("EREV", "برد افزوده"),
    ("HEV", "هیبرید"),
)

BRAND_ICON_SLUGS = frozenset(
    {
        "audi",
        "bmw",
        "byd",
        "honda",
        "hyundai",
        "mazda",
        "mercedes-benz",
        "mitsubishi",
        "toyota",
        "volkswagen",
        "volvo",
    }
)

CONNECTOR_ICON_FILES = {
    "AC_GBT": "Gbt_ac.svg",
    "AC_TYPE1": "Type1_J1772.svg",
    "AC_TYPE2": "Type2_socket.svg",
    "DC_GBT": "Gbt_dc.svg",
    "DC_CCS2": "Type2_CCS.svg",
    "DC_CHADEMO": "Chademo_type4.svg",
}


def fa_number(value: float) -> str:
    number = float(value)
    if number.is_integer():
        text = str(int(number))
    else:
        text = f"{number:.2f}".rstrip("0").rstrip(".")
    return text.translate(_DIGIT)


def _compact(value: str) -> str:
    text = value.translate(_SEARCH).lower().replace(".", "").replace("+", "")
    return re.sub(r"[^\w]+", "", text, flags=re.UNICODE)


def _join_fa(items: list[str]) -> str:
    if not items:
        return ""
    if len(items) == 1:
        return items[0]
    if len(items) == 2:
        return f"{items[0]} و {items[1]}"
    return "، ".join(items[:-1]) + " و " + items[-1]


def _battery_text(variant: VehicleVariant) -> str | None:
    low, high = variant.battery_kwh_min, variant.battery_kwh_max
    if low is None and high is None:
        return None
    if low is not None and high is not None and low != high:
        return f"{fa_number(low)} تا {fa_number(high)} کیلووات‌ساعت"
    number = high if high is not None else low
    assert number is not None
    return f"{fa_number(number)} کیلووات‌ساعت"


def _lead(variant: VehicleVariant) -> str:
    sentences = [f"{variant.display_name} خودروی {variant.powertrain_label} است."]
    if variant.importer_name_fa:
        sentences.append(f"در این فهرست با واردکننده {variant.importer_name_fa} ثبت شده است.")
    else:
        sentences.append("واردکنندهٔ آن در منبع ثبت نشده است.")

    facts: list[str] = []
    battery = _battery_text(variant)
    if battery:
        facts.append(f"باتری {battery}")
    if variant.range_km is not None:
        standard = f" ({variant.range_standard})" if variant.range_standard else ""
        facts.append(f"برد ثبت‌شده {fa_number(variant.range_km)} کیلومتر{standard}")
    if facts:
        sentences.append(_join_fa(facts) + " است.")

    if variant.connectors:
        names = _join_fa([item.display_name for item in variant.connectors])
        sentences.append(f"سوکت شارژ این مدل {names} است.")
    if variant.ac_charge_limit_kw is not None:
        sentences.append(f"سقف شارژ AC در منبع {fa_number(variant.ac_charge_limit_kw)} کیلووات است.")
    if variant.dc_charge_limit_kw is not None:
        sentences.append(f"سقف شارژ DC در منبع {fa_number(variant.dc_charge_limit_kw)} کیلووات است.")
    return " ".join(sentences)


def _description(variant: VehicleVariant) -> str:
    text = _lead(variant)
    if variant.warnings:
        return f"{text} {' '.join(variant.warnings)}"
    return text


def _anchors(catalog: VehicleCatalog) -> dict[str, str]:
    used: set[str] = set()
    anchors: dict[str, str] = {}
    for make in catalog.makes:
        for model in make.models:
            for variant in model.variants:
                base = f"{make.slug}-{variant.model_slug}"
                if variant.model_year:
                    base = f"{base}-{variant.model_year}"
                anchor = base
                suffix = 2
                while anchor in used:
                    anchor = f"{base}-{suffix}"
                    suffix += 1
                used.add(anchor)
                anchors[variant.id] = anchor
    return anchors


def _matching(catalog: VehicleCatalog, code: str) -> list[VehicleVariant]:
    return [variant for variant in catalog.variants() if any(item.code == code for item in variant.connectors)]


def _sample(variants: list[VehicleVariant], limit: int = 4) -> str:
    names = [variant.display_name for variant in variants]
    if len(names) <= limit:
        return _join_fa(names)
    return "، ".join(names[:limit]) + " و چند مدل دیگر"


def _faq() -> list[tuple[str, str]]:
    return [
        (
            "چه خودروهایی در این فهرست هستند؟",
            "مدل‌هایی که در کاتالوگ EV98 برای بازار ایران ثبت شده‌اند: خودروی برقی، پلاگین‌هیبرید و چند مدل با برد افزوده. "
            "این صفحه ادعای پوشش همهٔ خودروهای پلاک‌شده در کشور را ندارد.",
        ),
        (
            "خودروهای وارداتی با چه سوکتی شارژ می‌شوند؟",
            "بیشتر مدل‌های این فهرست شارژ سریع GB/T دارند، که استاندارد رایج بازار چین است. "
            "گروهی Type 2 و CCS2 دارند و میتسوبیشی اوتلندر Type 1 و CHAdeMO است. سوکت دقیق هر مدل روی کارت همان خودرو نوشته شده.",
        ),
        (
            "خودروی GB/T در ایستگاه CCS2 شارژ می‌شود؟",
            "خیر. ایستگاه باید همان استاندارد سوکت خودرو را داشته باشد. تبدیل بین GB/T و CCS2 همیشه در دسترس یا مناسب شارژ سریع نیست. "
            "با انتخاب خودرو در EV98، نقشه ایستگاه‌هایی را نشان می‌دهد که دست‌کم یکی از سوکت‌های همان خودرو را دارند.",
        ),
        (
            "برد نوشته‌شده همان برد واقعی رانندگی است؟",
            "خیر. بیشتر عددها NEDC هستند و در چرخهٔ آزمایشگاهی ثبت شده‌اند. برد در جاده، به‌خصوص با کولر یا سرعت بالا، کمتر است. "
            "برای پلاگین‌هیبرید هم ممکن است عدد، برد برقی یا برد ترکیبی منبع باشد؛ کنار هر عدد استاندارد همان منبع آمده است.",
        ),
        (
            "قیمت این خودروها را از کجا ببینم؟",
            "EV98 قیمت فروش اعلام نمی‌کند. این صفحه مشخصات شارژ و راه رسیدن به ایستگاه سازگار است، نه آگهی خرید.",
        ),
        (
            "اگر سوکت خودروی من با این صفحه فرق داشت چه کار کنم؟",
            "برای برخی مدل‌ها، از جمله فولکس‌واگن، منبع هشدار داده که بسته به واردکننده درگاه شارژ ممکن است فرق کند. "
            "درگاه روی خودرو یا دفترچه را با این فهرست مقایسه کنید و اگر مطمئن نیستید، روی نقشه سوکت را خودتان فیلتر کنید.",
        ),
    ]


def _json_ld(catalog: VehicleCatalog, anchors: dict[str, str]) -> str:
    variants = catalog.variants()
    items = []
    for index, variant in enumerate(variants, start=1):
        make_name = next(make.name_fa for make in catalog.makes if any(model.variants and variant in model.variants for model in make.models))
        car: dict[str, object] = {
            "@type": "Car",
            "name": variant.display_name,
            "brand": {"@type": "Brand", "name": make_name},
            "fuelType": FUEL_TYPE.get(variant.powertrain_type, variant.powertrain_label),
            "url": f"{CARS_URL}#{anchors[variant.id]}",
            "description": _description(variant),
        }
        if variant.model_year:
            car["vehicleModelDate"] = str(variant.model_year)
        items.append({"@type": "ListItem", "position": index, "item": car})

    graph: list[dict[str, object]] = [
        {
            "@type": "CollectionPage",
            "@id": f"{CARS_URL}#page",
            "url": CARS_URL,
            "name": TITLE,
            "description": DESCRIPTION,
            "inLanguage": "fa-IR",
            "dateModified": CARS_UPDATED.isoformat(),
            "isPartOf": {"@type": "WebSite", "@id": f"{SITE}/#website", "name": "EV98", "url": f"{SITE}/"},
            "publisher": {"@type": "Organization", "name": "EV98", "url": f"{SITE}/"},
            "breadcrumb": {"@id": f"{CARS_URL}#breadcrumb"},
            "mainEntity": {"@id": f"{CARS_URL}#list"},
        },
        {
            "@type": "WebSite",
            "@id": f"{SITE}/#website",
            "name": "EV98",
            "url": f"{SITE}/",
            "inLanguage": "fa-IR",
        },
        {
            "@type": "BreadcrumbList",
            "@id": f"{CARS_URL}#breadcrumb",
            "itemListElement": [
                {"@type": "ListItem", "position": 1, "name": "EV98", "item": f"{SITE}/"},
                {"@type": "ListItem", "position": 2, "name": "خودروهای برقی وارداتی", "item": CARS_URL},
            ],
        },
        {
            "@type": "ItemList",
            "@id": f"{CARS_URL}#list",
            "name": "فهرست خودروهای برقی وارد شده به ایران",
            "numberOfItems": len(items),
            "itemListElement": items,
        },
        {
            "@type": "FAQPage",
            "@id": f"{CARS_URL}#faq",
            "mainEntity": [
                {
                    "@type": "Question",
                    "name": question,
                    "acceptedAnswer": {"@type": "Answer", "text": answer},
                }
                for question, answer in _faq()
            ],
        },
    ]
    payload = json.dumps({"@context": "https://schema.org", "@graph": graph}, ensure_ascii=False)
    return payload.replace("<", "\\u003c")


def _standards_html(catalog: VehicleCatalog) -> str:
    total = len(catalog.variants())
    gbt = _matching(catalog, "DC_GBT")
    ccs = _matching(catalog, "DC_CCS2")
    chademo = _matching(catalog, "DC_CHADEMO")
    no_dc = [variant for variant in catalog.variants() if variant.no_dc_declared]
    paragraphs = [
        "در ایران چند استاندارد شارژ کنار هم استفاده می‌شود و خودرو فقط با ایستگاهی شارژ می‌شود که همان سوکت را داشته باشد.",
        (
            f"از {fa_number(total)} مدل این صفحه، {fa_number(len(gbt))} مدل شارژ سریع GB/T دارند"
            f" (از جمله {_sample(gbt)})، {fa_number(len(ccs))} مدل CCS2"
            f" (از جمله {_sample(ccs)}) و {fa_number(len(chademo))} مدل CHAdeMO"
            f" ({_sample(chademo)})."
        ),
        "GB/T استاندارد رایج بازار چین است. Type 2 شارژ AC اروپایی است و CCS2 شارژ سریع همان خانواده. این سوکت‌ها به‌جای هم کار نمی‌کنند.",
    ]
    if no_dc:
        paragraphs.append(
            "برای این مدل‌ها ورودی شارژ سریع DC در منبع اعلام نشده: "
            + _sample(no_dc, limit=8)
            + ". روی نقشه ممکن است فقط ایستگاه AC سازگار پیدا شود."
        )
    body = "".join(f"<p>{escape(text)}</p>" for text in paragraphs)
    return (
        '<section id="standards" aria-labelledby="standards-title">'
        '<h2 id="standards-title">سوکت شارژ خودروهای وارداتی</h2>'
        f"{body}</section>"
    )


def _brand_mark(icon: str | None, name_en: str) -> str:
    if icon in BRAND_ICON_SLUGS:
        return (
            f'<img class="brand-mark" src="/brand-icons/{escape(icon or "", quote=True)}.svg"'
            ' alt="" width="36" height="36">'
        )
    letter = escape((name_en[:1] or "•").upper())
    return f'<span class="brand-fallback" aria-hidden="true">{letter}</span>'


def _connector_fact(connector) -> str:
    file_name = CONNECTOR_ICON_FILES.get(connector.code)
    icon = ""
    if file_name:
        icon = (
            f'<img class="connector-icon" src="/connector-icons/{escape(file_name, quote=True)}"'
            ' alt="" width="28" height="28">'
        )
    return f"<li>{icon}سوکت {escape(connector.display_name)}</li>"


def _catalog_html(catalog: VehicleCatalog, anchors: dict[str, str]) -> str:
    present = {variant.powertrain_type for variant in catalog.variants()}
    chips = [
        (
            '<button type="button" data-power="all" aria-pressed="true">همه</button>'
        )
    ]
    chips.extend(
        f'<button type="button" data-power="{code}" aria-pressed="false">{escape(label)}</button>'
        for code, label in POWER_FILTERS
        if code != "all" and code in present
    )
    sections: list[str] = []
    for make in catalog.makes:
        cards: list[str] = []
        for model in make.models:
            for variant in model.variants:
                lead = _lead(variant)
                search = " ".join(
                    token
                    for token in (
                        _compact(variant.display_name),
                        _compact(make.name_fa),
                        _compact(make.name_en),
                        _compact(variant.model_name),
                        _compact(variant.importer_name_fa or ""),
                        _compact(variant.importer_name or ""),
                        _compact(variant.powertrain_label),
                        *(_compact(item.display_name) for item in variant.connectors),
                    )
                    if token
                )
                facts: list[str] = []
                if variant.importer_name_fa:
                    facts.append(f"<li>واردکننده: {escape(variant.importer_name_fa)}</li>")
                else:
                    facts.append("<li>واردکننده در منبع ثبت نشده</li>")
                battery = _battery_text(variant)
                if battery:
                    facts.append(f"<li>باتری: {escape(battery)}</li>")
                if variant.range_km is not None:
                    standard = f" ({escape(variant.range_standard)})" if variant.range_standard else ""
                    facts.append(f"<li>برد ثبت‌شده: {fa_number(variant.range_km)} کیلومتر{standard}</li>")
                for connector in variant.connectors:
                    facts.append(_connector_fact(connector))
                if variant.ac_charge_limit_kw is not None:
                    facts.append(f"<li>سقف شارژ AC: {fa_number(variant.ac_charge_limit_kw)} کیلووات</li>")
                if variant.dc_charge_limit_kw is not None:
                    facts.append(f"<li>سقف شارژ DC: {fa_number(variant.dc_charge_limit_kw)} کیلووات</li>")
                note = ""
                if variant.warnings:
                    note = f'<p class="note"><strong>توجه:</strong> {escape(" ".join(variant.warnings))}</p>'
                cards.append(
                    "<article"
                    f' id="{anchors[variant.id]}"'
                    ' data-car'
                    f' data-powertrain="{escape(variant.powertrain_type, quote=True)}"'
                    f' data-search="{escape(search, quote=True)}">'
                    f'<div class="car-title">{_brand_mark(make.icon, make.name_en)}'
                    f"<h4>{escape(variant.display_name)}</h4></div>"
                    f"<p>{escape(lead)}</p>"
                    f"<ul>{''.join(facts)}</ul>"
                    f"{note}"
                    f'<a class="car-cta" href="/?vehicle={escape(variant.id, quote=True)}">شارژرهای سازگار روی نقشه</a>'
                    "</article>"
                )
        sections.append(
            f'<section class="make" data-make>'
            f"<h3>{_brand_mark(make.icon, make.name_en)}<span>{escape(make.name_fa)}</span></h3>"
            f'<div class="car-grid">{"".join(cards)}</div>'
            "</section>"
        )
    count = fa_number(len(catalog.variants()))
    return (
        '<section id="list" aria-labelledby="list-title">'
        '<h2 id="list-title">فهرست خودروها</h2>'
        '<form class="finder" id="car-finder" role="search">'
        '<div class="field"><label for="car-query">جستجو در نام، برند یا واردکننده</label>'
        '<input id="car-query" name="q" type="search" autocomplete="off" enterkeyhint="search"></div>'
        f'<div class="chips" role="group" aria-label="نوع قوای محرکه">{"".join(chips)}</div>'
        "</form>"
        f'<p class="count" aria-live="polite"><span id="car-count">{count}</span> مدل در این فهرست</p>'
        '<p id="car-empty" hidden>خودرویی با این عبارت در فهرست نیست.</p>'
        f"{''.join(sections)}"
        "</section>"
    )


def _faq_html() -> str:
    blocks = []
    for question, answer in _faq():
        blocks.append(f"<h3>{escape(question)}</h3><p>{escape(answer)}</p>")
    return (
        '<section id="faq" aria-labelledby="faq-title">'
        '<h2 id="faq-title">پرسش‌های متداول</h2>'
        f"{''.join(blocks)}</section>"
    )


GTAG = """<!-- Google tag (gtag.js) -->
<script async src="https://www.googletagmanager.com/gtag/js?id=G-2EZDZLWKS1"></script>
<script>
  window.dataLayer = window.dataLayer || [];
  function gtag(){dataLayer.push(arguments);}
  gtag('js', new Date());

  gtag('config', 'G-2EZDZLWKS1');
</script>
"""

CSS = """
:root {
  color-scheme: light;
  --ink: #102a27;
  --muted: #526864;
  --line: rgba(21, 73, 67, 0.14);
  --line-strong: rgba(21, 73, 67, 0.24);
  --surface: #ffffff;
  --soft: #f1f7f5;
  --page: #e8f0ee;
  --pine: #087a65;
  --pine-strong: #056150;
  --pine-soft: #dff3ed;
  --hero: #0c2420;
  --hero-ink: #f4fbf9;
  --hero-muted: #d5ebe4;
  --amber: #9a5b08;
}
* { box-sizing: border-box; }
html, body { margin: 0; }
html { scroll-padding-top: 80px; }
section, article { scroll-margin-top: 80px; }
body {
  background:
    radial-gradient(1200px 420px at 100% -80px, rgba(8, 122, 101, 0.16), transparent 60%),
    var(--page);
  color: var(--ink);
  font-family: Vazirmatn, Tahoma, sans-serif;
  font-size: 16px;
  line-height: 1.7;
}
a { color: var(--pine-strong); }
:focus-visible { outline: 3px solid rgba(8, 122, 101, 0.55); outline-offset: 3px; }
.skip {
  position: absolute;
  z-index: 10;
  top: 12px;
  inset-inline-start: 12px;
  transform: translateY(-150%);
  background: var(--ink);
  color: var(--hero-ink);
  text-decoration: none;
  border-radius: 12px;
  padding: 10px 14px;
}
.skip:focus { transform: none; }
.site-header {
  position: sticky;
  top: 0;
  z-index: 5;
  background: rgba(249, 252, 251, 0.92);
  border-bottom: 1px solid var(--line);
  backdrop-filter: blur(16px);
}
.bar, .wrap { width: min(1080px, calc(100% - 32px)); margin-inline: auto; }
.bar {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 16px;
  min-height: 64px;
}
.logo { display: inline-flex; align-items: center; min-height: 48px; }
.logo img { display: block; height: 32px; width: auto; }
.nav-link {
  display: inline-flex;
  align-items: center;
  min-height: 44px;
  padding: 8px 14px;
  border-radius: 14px;
  background: var(--surface);
  border: 1px solid var(--line-strong);
  color: var(--ink);
  text-decoration: none;
  font-weight: 700;
}
.hero { background: var(--hero); color: var(--hero-ink); }
.hero-inner { width: min(1080px, calc(100% - 32px)); margin-inline: auto; padding: 28px 0 36px; }
.crumb { display: flex; flex-wrap: wrap; gap: 8px; margin: 0 0 16px; padding: 0; list-style: none; color: var(--hero-muted); font-size: 14px; }
.crumb a { color: var(--hero-ink); font-weight: 700; }
.hero h1 {
  margin: 0;
  max-width: 18ch;
  font-size: clamp(28px, 4vw, 44px);
  line-height: 1.3;
  text-wrap: balance;
}
.lede { max-width: 68ch; margin: 16px 0 0; color: var(--hero-muted); font-size: 18px; }
.actions { display: flex; flex-wrap: wrap; gap: 8px; margin-top: 24px; }
.cta {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  min-height: 48px;
  padding: 12px 18px;
  border-radius: 14px;
  text-decoration: none;
  font-weight: 700;
}
.cta.primary { background: var(--hero-ink); color: var(--hero); }
.cta.secondary { color: var(--hero-ink); border: 1px solid rgba(244, 251, 249, 0.72); }
.stats { display: flex; flex-wrap: wrap; gap: 8px; margin: 24px 0 0; padding: 0; list-style: none; }
.stats li {
  min-width: 140px;
  padding: 12px 14px;
  border-radius: 14px;
  background: rgba(244, 251, 249, 0.08);
  border: 1px solid rgba(244, 251, 249, 0.16);
}
.stats strong { display: block; font-size: 24px; line-height: 1.3; }
.stats span { color: var(--hero-muted); font-size: 14px; }
main { padding: 8px 0 32px; }
section { margin-top: 28px; }
h2 { margin: 0 0 12px; font-size: clamp(22px, 3vw, 30px); line-height: 1.35; }
h3 { margin: 20px 0 8px; font-size: 22px; }
p { margin: 0 0 12px; }
.finder { display: grid; gap: 12px; margin-bottom: 8px; }
.field { display: grid; gap: 6px; }
.finder label { font-weight: 700; }
.finder input {
  width: 100%;
  min-height: 48px;
  margin: 0;
  padding: 10px 12px;
  border: 1px solid var(--line-strong);
  border-radius: 12px;
  background: var(--surface);
  color: var(--ink);
  font: inherit;
}
.chips { display: flex; flex-wrap: wrap; gap: 8px; }
.chips button {
  min-height: 44px;
  padding: 8px 14px;
  border: 1px solid var(--line-strong);
  border-radius: 999px;
  background: var(--surface);
  color: var(--ink);
  font: inherit;
  font-weight: 700;
}
.chips button[aria-pressed="true"] { background: var(--pine-soft); border-color: var(--pine); color: var(--pine-strong); }
.count { color: var(--muted); font-weight: 700; }
.make { margin-top: 28px; }
.make > h3 {
  display: flex;
  align-items: center;
  gap: 10px;
  margin: 0 0 12px;
  padding-bottom: 8px;
  border-bottom: 1px solid var(--line);
}
.car-title { display: flex; align-items: center; gap: 10px; }
.brand-mark {
  width: 36px;
  height: 36px;
  flex: none;
  object-fit: contain;
}
.brand-fallback {
  display: inline-grid;
  place-items: center;
  width: 36px;
  height: 36px;
  flex: none;
  border-radius: 10px;
  border: 1px solid rgba(8, 122, 101, 0.18);
  background: var(--pine-soft);
  color: var(--pine-strong);
  font-size: 15px;
  font-weight: 700;
}
.car-grid { display: grid; gap: 12px; }
.car-grid article {
  display: flex;
  flex-direction: column;
  gap: 8px;
  padding: 16px;
  background: var(--surface);
  border: 1px solid var(--line);
  border-radius: 16px;
}
.car-grid h4 { margin: 0; font-size: 20px; line-height: 1.4; }
.car-grid p { margin: 0; }
.car-grid ul { margin: 0; padding: 0; list-style: none; display: flex; flex-wrap: wrap; gap: 6px; }
.car-grid li {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  padding: 4px 8px;
  border-radius: 8px;
  background: var(--soft);
  font-size: 14px;
  line-height: 1.5;
}
.connector-icon {
  width: 28px;
  height: 28px;
  flex: none;
  object-fit: contain;
}
.note {
  padding: 8px 12px;
  border-inline-start: 3px solid var(--amber);
  background: #fbf6ee;
  border-radius: 8px;
}
.car-cta {
  align-self: start;
  display: inline-flex;
  align-items: center;
  min-height: 44px;
  margin-top: auto;
  padding: 8px 12px;
  border-radius: 12px;
  background: var(--pine-strong);
  color: var(--hero-ink);
  text-decoration: none;
  font-weight: 700;
}
#standards, #how, #faq {
  padding: 20px;
  background: rgba(255, 255, 255, 0.72);
  border: 1px solid var(--line);
  border-radius: 16px;
}
#how ol { margin: 0; padding-inline-start: 20px; }
#how li + li { margin-top: 8px; }
.site-footer {
  width: min(1080px, calc(100% - 32px));
  margin: 0 auto;
  padding: 8px 0 calc(28px + env(safe-area-inset-bottom, 0px));
  color: var(--muted);
}
.site-footer a { font-weight: 700; }
@media (min-width: 840px) {
  .car-grid { grid-template-columns: 1fr 1fr; }
  .hero-inner, .bar { width: min(1080px, calc(100% - 48px)); }
  .wrap, .site-footer, .hero-inner { width: min(1080px, calc(100% - 48px)); }
}
@media (hover: hover) {
  .nav-link:hover, .cta.primary:hover { background: var(--pine-soft); }
  .car-cta:hover { background: var(--pine); }
}
@media (prefers-reduced-motion: reduce) {
  * { scroll-behavior: auto !important; }
}
"""

FILTER_JS = """
const form = document.getElementById("car-finder");
const input = document.getElementById("car-query");
const count = document.getElementById("car-count");
const empty = document.getElementById("car-empty");
function compact(value) {
  return value
    .replace(/[يىئ]/g, "ی")
    .replace(/ك/g, "ک")
    .replace(/[أإآ]/g, "ا")
    .replace(/ة/g, "ه")
    .replace(/ؤ/g, "و")
    .replace(/\\u200c/g, "")
    .toLowerCase()
    .replace(/[.+]/g, "")
    .replace(/[^\\p{L}\\p{N}]+/gu, "");
}
function toFa(value) {
  return String(value).replace(/\\d/g, (digit) => "۰۱۲۳۴۵۶۷۸۹"[digit]);
}
function apply() {
  const query = compact(input.value);
  const power = form.querySelector('[aria-pressed="true"]')?.dataset.power || "all";
  let shown = 0;
  document.querySelectorAll("[data-car]").forEach((card) => {
    const blob = (card.dataset.search || "").replace(/ /g, "");
    const visible = (power === "all" || card.dataset.powertrain === power) && (!query || blob.includes(query));
    card.hidden = !visible;
    if (visible) shown += 1;
  });
  document.querySelectorAll("[data-make]").forEach((section) => {
    section.hidden = section.querySelector("[data-car]:not([hidden])") == null;
  });
  count.textContent = toFa(shown);
  empty.hidden = shown !== 0;
}
form.addEventListener("submit", (event) => { event.preventDefault(); apply(); });
input.addEventListener("input", apply);
form.querySelectorAll("[data-power]").forEach((button) => {
  button.addEventListener("click", () => {
    form.querySelectorAll("[data-power]").forEach((item) => item.setAttribute("aria-pressed", "false"));
    button.setAttribute("aria-pressed", "true");
    apply();
  });
});
"""


def render_cars_page(catalog: VehicleCatalog) -> str:
    variants = catalog.variants()
    anchors = _anchors(catalog)
    bev = sum(1 for variant in variants if variant.powertrain_type == "BEV")
    stats = (
        f"<li><strong>{fa_number(len(variants))}</strong><span>مدل در کاتالوگ</span></li>"
        f"<li><strong>{fa_number(len(catalog.makes))}</strong><span>برند</span></li>"
        f"<li><strong>{fa_number(bev)}</strong><span>خودروی برقی</span></li>"
    )
    intro = (
        "خودروهای برقی وارد شده به ایران سوکت یکسانی ندارند. "
        "این صفحه مدل‌هایی را فهرست می‌کند که در کاتالوگ EV98 برای بازار ایران ثبت شده‌اند: "
        "خودروی برقی، پلاگین‌هیبرید و مدل‌های برد افزوده. "
        "برای هر کدام واردکننده، ظرفیت باتری، برد ثبت‌شده در منبع و نوع سوکت شارژ آمده است "
        "تا ایستگاه ناسازگار را کنار بگذارید."
    )
    how = (
        '<section id="how" aria-labelledby="how-title">'
        '<h2 id="how-title">پیدا کردن ایستگاه سازگار</h2>'
        "<ol>"
        "<li>مدل را در فهرست همین صفحه پیدا کنید.</li>"
        "<li>دکمهٔ «شارژرهای سازگار روی نقشه» را باز کنید.</li>"
        "<li>نقشه ایستگاه‌هایی را نشان می‌دهد که دست‌کم یکی از سوکت‌های همان خودرو را دارند.</li>"
        "</ol></section>"
    )
    updated = CARS_UPDATED.isoformat()
    return f"""<!doctype html>
<html lang="fa" dir="rtl">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  {GTAG}
  <title>{escape(TITLE)}</title>
  <meta name="description" content="{escape(DESCRIPTION)}">
  <meta name="robots" content="index, follow, max-image-preview:large">
  <meta name="theme-color" content="#0B1F1C">
  <link rel="canonical" href="{CARS_URL}">
  <link rel="alternate" hreflang="fa-IR" href="{CARS_URL}">
  <link rel="alternate" hreflang="x-default" href="{CARS_URL}">
  <meta property="og:type" content="website">
  <meta property="og:locale" content="fa_IR">
  <meta property="og:site_name" content="EV98">
  <meta property="og:title" content="{escape(TITLE)}">
  <meta property="og:description" content="{escape(DESCRIPTION)}">
  <meta property="og:url" content="{CARS_URL}">
  <meta property="og:image" content="{SITE}/og-image.png">
  <meta property="og:image:width" content="1200">
  <meta property="og:image:height" content="630">
  <meta property="og:image:alt" content="EV98 — نقشه ایستگاه‌های شارژ خودرو برقی ایران">
  <meta name="twitter:card" content="summary_large_image">
  <meta name="twitter:title" content="{escape(TITLE)}">
  <meta name="twitter:description" content="{escape(DESCRIPTION)}">
  <meta name="twitter:image" content="{SITE}/og-image.png">
  <link rel="icon" type="image/png" href="/favicon.png">
  <link rel="apple-touch-icon" href="/apple-touch-icon.png">
  <link rel="preconnect" href="https://fonts.googleapis.com">
  <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
  <link href="https://fonts.googleapis.com/css2?family=Vazirmatn:wght@420;560;700&amp;display=swap" rel="stylesheet">
  <script type="application/ld+json">{_json_ld(catalog, anchors)}</script>
  <style>{CSS}</style>
</head>
<body>
  <a class="skip" href="#main">رفتن به محتوا</a>
  <header class="site-header">
    <div class="bar">
      <a class="logo" href="/" aria-label="EV98، بازگشت به نقشه"><img src="/ev98-logo.png" alt="EV98" width="123" height="32"></a>
      <a class="nav-link" href="/">نقشه شارژ</a>
    </div>
  </header>
  <section class="hero">
    <div class="hero-inner">
      <nav aria-label="مسیر">
        <ol class="crumb">
          <li><a href="/">EV98</a></li>
          <li aria-current="page">خودروهای برقی وارداتی</li>
        </ol>
      </nav>
      <h1>خودروهای برقی وارد شده به ایران</h1>
      <p class="lede">{escape(intro)}</p>
      <ul class="stats">{stats}</ul>
      <div class="actions">
        <a class="cta primary" href="#list">دیدن فهرست خودروها</a>
        <a class="cta secondary" href="/">نقشه ایستگاه‌های شارژ</a>
      </div>
    </div>
  </section>
  <main id="main" class="wrap">
    {_catalog_html(catalog, anchors)}
    {_standards_html(catalog)}
    {how}
    {_faq_html()}
  </main>
  <footer class="site-footer">
    <p><a href="/">EV98</a> نقشه ایستگاه‌های شارژ خودرو برقی ایران. مشخصات این صفحه از کاتالوگ همین سایت است و قیمت فروش نیست.</p>
    <p>آخرین به‌روزرسانی <time datetime="{updated}">{fa_number(CARS_UPDATED.day)} سپتامبر {fa_number(CARS_UPDATED.year)}</time>.</p>
  </footer>
  <script>{FILTER_JS}</script>
</body>
</html>
"""
