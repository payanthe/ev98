"""Normalized vehicle catalog from the eMapna snapshot.

The CSV in ``outputs/emapna_ev_dataset`` is a source extract, not the record a
user selects. This module turns each row into a make, a model, and a variant
with separate AC and DC connectors, matching the vehicle schema. Selection ids
are uuid5 values of the eMapna external id so they stay stable without a
database row yet.
"""

from __future__ import annotations

import csv
import re
import uuid
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

from app.domain.text import normalize_fa

VARIANT_NAMESPACE = uuid.UUID("6f1c1c2e-7a4e-5b1a-9c3d-0e0980000001")

DATASET_PATH = (
    Path(__file__).resolve().parents[3] / "outputs" / "emapna_ev_dataset" / "emapna_ev_normalized.csv"
)

# Most → least common in live charging.connectors inventory.
STATION_ORDER = ["CCS_2", "GBT_DC", "GBT_AC", "TYPE_2", "CHADEMO", "TYPE_1"]

CONNECTORS: dict[str, dict[str, str]] = {
    "AC_GBT": {"display_name": "GB/T AC", "current_type": "AC", "emapna_name": "Car-AC-GB/T", "station_standard": "GBT_AC"},
    "AC_TYPE1": {"display_name": "Type 1", "current_type": "AC", "emapna_name": "Car-AC-Type1", "station_standard": "TYPE_1"},
    "AC_TYPE2": {"display_name": "Type 2", "current_type": "AC", "emapna_name": "Car-AC-Type2", "station_standard": "TYPE_2"},
    "DC_GBT": {"display_name": "GB/T DC", "current_type": "DC", "emapna_name": "Car-DC-GB/T", "station_standard": "GBT_DC"},
    "DC_CCS2": {"display_name": "CCS2", "current_type": "DC", "emapna_name": "Car-DC-CCS2", "station_standard": "CCS_2"},
    "DC_CHADEMO": {"display_name": "CHAdeMO", "current_type": "DC", "emapna_name": "Car-DC-CHAdeMO", "station_standard": "CHADEMO"},
}

CSV_FLAGS = {
    "acGbt": "AC_GBT",
    "acType1": "AC_TYPE1",
    "acType2": "AC_TYPE2",
    "dcGbt": "DC_GBT",
    "dcCcs2": "DC_CCS2",
    "dcChademo": "DC_CHADEMO",
}

# name_en, name_fa, icon slug or None, extra search aliases
MAKES: dict[str, tuple[str, str, str | None, tuple[str, ...]]] = {
    "volkswagen": ("Volkswagen", "فولکس‌واگن", "volkswagen", ("فولکس", "vw")),
    "audi": ("Audi", "آئودی", "audi", ("اودی",)),
    "arrizo": ("Arrizo", "آریزو", None, ("arizo",)),
    "honda": ("Honda", "هوندا", "honda", ()),
    "jac": ("JAC", "جک", None, ("جک",)),
    "faw": ("FAW", "فاو", None, ("bestune", "بستیون")),
    "luna": ("Luna", "لونا", None, ("jmev",)),
    "toyota": ("Toyota", "تویوتا", "toyota", ()),
    "skywell": ("Skywell", "اسکای‌ول", None, ("اسکای ول", "اسکایول")),
    "fownix": ("Fownix", "فونیکس", None, ()),
    "venucia": ("Venucia", "ونوسیا", None, ()),
    "mitsubishi": ("Mitsubishi", "میتسوبیشی", "mitsubishi", ()),
    "hongqi": ("Hongqi", "هونگچی", None, ("hongchi", "هونچی")),
    "avatr": ("Avatr", "آواتر", None, ()),
    "bmw": ("BMW", "ب‌ام‌و", "bmw", ("بی ام و", "بیامو", "ب ام و", "ب ام و")),
    "voyah": ("Voyah", "وویا", None, ()),
    "mg": ("MG", "ام‌جی", None, ("ام جی", "امجی")),
    "hyundai": ("Hyundai", "هیوندای", "hyundai", ()),
    "mercedes-benz": ("Mercedes-Benz", "مرسدس بنز", "mercedes-benz", ("بنز", "مرسدس", "mercedes")),
    "byd": ("BYD", "بی‌وای‌دی", "byd", ("بی وای دی", "بیوایدی")),
    "leapmotor": ("Leapmotor", "لیپ‌موتور", None, ("leap motor", "لیپ موتور")),
    "eres": ("Eres", "ارس", None, ()),
    "dongfeng": ("Dongfeng", "دانگ‌فنگ", None, ("dong feng", "دانگ فنگ")),
    "gac": ("GAC", "گک", None, ("aion", "آیون")),
    "xpeng": ("XPeng", "اکس‌پنگ", None, ("xpeng", "اکسپنگ")),
    "changan": ("Changan", "چانگان", None, ()),
    "volvo": ("Volvo", "ولوو", "volvo", ()),
    "mazda": ("Mazda", "مزدا", "mazda", ()),
    "roewe": ("Roewe", "رووی", None, ()),
}

BRAND_KEYS = {
    "volkswagen": "volkswagen",
    "audi": "audi",
    "arizo": "arrizo",
    "honda": "honda",
    "jac": "jac",
    "faw": "faw",
    "luna": "luna",
    "toyota": "toyota",
    "skywell": "skywell",
    "fownix": "fownix",
    "venucia": "venucia",
    "mitsubishi": "mitsubishi",
    "hongchi": "hongqi",
    "hongqi": "hongqi",
    "avatr": "avatr",
    "bmw": "bmw",
    "voyah": "voyah",
    "mg": "mg",
    "hyundai": "hyundai",
    "mercedes benz": "mercedes-benz",
    "mercedes-benz": "mercedes-benz",
    "byd": "byd",
    "leap motor": "leapmotor",
    "leapmotor": "leapmotor",
    "eres": "eres",
    "dong feng": "dongfeng",
    "dongfeng": "dongfeng",
    "gac": "gac",
    "xpeng": "xpeng",
    "changan": "changan",
    "volvo": "volvo",
    "mazda": "mazda",
    "roewe": "roewe",
}

MODEL_NAMES = {
    "id4 crozz": "ID.4 Crozz",
    "q5 e-tron": "Q5 e-tron",
    "ev5 (arizo5)": "EV5",
    "ens1": "e:NS1",
    "ej7 (j7)": "EJ7",
    "id unyx": "ID. UNYX",
    "bestune nat": "Bestune NAT",
    "jmev yi": "Yi",
    "bz3(bz3x)": "bZ3X",
    "bz4 (bz4x)": "bZ4X",
    "et5": "ET5",
    "f8 pro e+": "F8 Pro e+",
    "v-online -dd-i": "V-Online DD-i",
    "d60ev plus": "D60 EV Plus",
    "outlander": "Outlander",
    "eqm5": "EQM5",
    "avatr11": "11",
    "hybrid": "Hybrid",
    "ix1": "iX1",
    "free": "Free",
    "mg4": "MG4",
    "q4 e-tron": "Q4 e-tron",
    "fx ev": "FX EV",
    "song plus": "Song Plus",
    "ioniq": "Ioniq",
    "eqb": "EQB",
    "eqa": "EQA",
    "eqe": "EQE",
    "qin l": "Qin L",
    "id4 unyx": "ID.4 Unyx",
    "t03": "T03",
    "m5": "M5",
    "ix3": "iX3",
    "e70": "E70",
    "f7 pro e+": "F7 Pro e+",
    "erx5": "ERX5",
    "aion v plus": "Aion V Plus",
    "aion s plus": "Aion S Plus",
    "g6": "G6",
    "eado ev460": "Eado EV460",
    "nevo a05": "Nevo A05",
    "ex30": "EX30",
    "ez-6": "EZ-6",
}

IMPORTERS = {
    "mammut khodro": ("ماموت خودرو", "mammut-khodro"),
    "moin khodro": ("معین خودرو", "moin-khodro"),
    "modiran khodro": ("مدیران خودرو", "modiran-khodro"),
    "kerman motor": ("کرمان موتور", "kerman-motor"),
    "iran khodro": ("ایران‌خودرو", "iran-khodro"),
    "barsavosh": ("برساوش", "barsavosh"),
    "nebka": ("نبکا", "nebka"),
    "tigard motor": ("تیگارد موتور", "tigard-motor"),
    "max motor": ("مکس موتور", "max-motor"),
    "arian motor": ("آرین موتور", "arian-motor"),
    "bahman motor": ("بهمن موتور", "bahman-motor"),
    "persia khodro": ("پرشیا خودرو", "persia-khodro"),
    "soroush motor": ("سروش موتور", "soroush-motor"),
    "nadin khodro": ("نادین خودرو", "nadin-khodro"),
    "hermes khodro": ("هرمس خودرو", "hermes-khodro"),
    "rasa motor": ("راسا موتور", "rasa-motor"),
    "shetabran khodro": ("شتابران خودرو", "shetabran-khodro"),
    "pars khodro": ("پارس خودرو", "pars-khodro"),
    "police-taxi driver": ("ناوگان تاکسی و پلیس", "police-taxi"),
    "shiran volt": ("شیران ولت", "shiran-volt"),
    "saipa": ("سایپا", "saipa"),
    "farda motors": ("فردا موتورز", "farda-motors"),
    "aftab khodro": ("آفتاب خودرو", "aftab-khodro"),
}

POWERTRAIN_LABELS = {
    "BEV": "برقی",
    "PHEV": "پلاگین هیبرید",
    "EREV": "برقی با برد افزوده",
    "HEV": "هیبرید",
}

_YEAR = re.compile(r"[\s\-]+((?:19|20)\d{2})\s*$")
_KW = re.compile(r"(\d+(?:\.\d+)?)\s*k\s*w", re.IGNORECASE)


@dataclass(frozen=True)
class VehicleConnector:
    code: str
    display_name: str
    current_type: str
    station_standard: str


@dataclass(frozen=True)
class VehicleVariant:
    id: str
    model_slug: str
    model_name: str
    variant_name: str
    display_name: str
    model_year: int | None
    powertrain_type: str
    powertrain_label: str
    battery_kwh_min: float | None
    battery_kwh_max: float | None
    range_km: float | None
    range_standard: str | None
    ac_charge_limit_kw: float | None
    dc_charge_limit_kw: float | None
    connectors: tuple[VehicleConnector, ...]
    station_standards: tuple[str, ...]
    importer_name: str | None
    importer_name_fa: str | None
    verification_status: str
    warnings: tuple[str, ...]
    no_dc_declared: bool
    search: str
    source_external_id: str


@dataclass(frozen=True)
class VehicleModel:
    slug: str
    name: str
    variants: tuple[VehicleVariant, ...]


@dataclass(frozen=True)
class VehicleMake:
    slug: str
    name_en: str
    name_fa: str
    icon: str | None
    models: tuple[VehicleModel, ...]


@dataclass(frozen=True)
class VehicleCatalog:
    makes: tuple[VehicleMake, ...]

    def variants(self) -> list[VehicleVariant]:
        return [variant for make in self.makes for model in make.models for variant in model.variants]

    def get(self, variant_id: str) -> VehicleVariant | None:
        for variant in self.variants():
            if variant.id == variant_id:
                return variant
        return None


def _brand_key(value: str) -> str | None:
    text = re.sub(r"\s+", " ", value.strip().casefold().replace("-", " ").replace("_", " "))
    return BRAND_KEYS.get(text)


def _compact_key(value: str) -> str:
    text = normalize_fa(value).replace(".", " ").replace("+", " ")
    text = re.sub(r"[^\w\s]", " ", text, flags=re.UNICODE)
    return re.sub(r"\s+", " ", text).strip()


MODEL_BY_KEY = {_compact_key(key): name for key, name in MODEL_NAMES.items()}


def _search_blob(values: list[str]) -> str:
    keys: set[str] = set()
    for value in values:
        normalized = _compact_key(value)
        if normalized:
            keys.add(normalized.replace(" ", ""))
    return " ".join(sorted(keys))


def _slug(value: str) -> str:
    text = value.casefold().replace("&", " ")
    text = re.sub(r"[^a-z0-9]+", "-", text).strip("-")
    return text or "model"


def _number(value: str | None) -> float | None:
    text = (value or "").strip()
    if not text:
        return None
    return float(text)


def _flag(value: str | None) -> bool:
    return (value or "").strip().lower() == "true"


def _split_importer(raw: str) -> tuple[str | None, str | None]:
    lines = [line.strip() for line in (raw or "").splitlines() if line.strip()]
    if not lines:
        return None, None
    notes = " ".join(lines[1:]) or None
    return lines[0], notes


def _parse_charge_limit(raw: str) -> tuple[float | None, str | None]:
    match = _KW.search(raw or "")
    if not match:
        return None, None
    upper = raw.upper()
    kind = "AC" if "AC" in upper else "DC" if "DC" in upper else None
    return float(match.group(1)), kind


def _tidy_model(raw_model: str) -> tuple[str, int | None]:
    text = raw_model.strip()
    year = None
    match = _YEAR.search(text)
    if match:
        year = int(match.group(1))
        text = text[: match.start()].strip(" -")
    name = MODEL_BY_KEY.get(_compact_key(text), text)
    return name, year


def _resolve_make_model(brand: str, model: str) -> tuple[str, str]:
    brand_key = _brand_key(brand)
    model_key = _brand_key(model)
    if model_key in MAKES and brand_key not in MAKES:
        return model_key, brand.strip()
    if brand_key not in MAKES:
        raise ValueError(f"unknown make: {brand}")
    return brand_key, model.strip()


def _variant_id(external_id: str) -> str:
    return str(uuid.uuid5(VARIANT_NAMESPACE, f"emapna:{external_id}"))


def _row_to_variant(row: dict[str, str]) -> tuple[str, VehicleVariant]:
    make_slug, raw_model = _resolve_make_model(row["brand"], row["model"])
    make_en, make_fa, _icon, extra_aliases = MAKES[make_slug]
    model_name, model_year = _tidy_model(raw_model)
    model_slug = _slug(model_name)

    codes = [code for column, code in CSV_FLAGS.items() if _flag(row.get(column))]
    connectors = tuple(
        VehicleConnector(
            code=code,
            display_name=CONNECTORS[code]["display_name"],
            current_type=CONNECTORS[code]["current_type"],
            station_standard=CONNECTORS[code]["station_standard"],
        )
        for code in codes
    )
    station_standards = tuple(
        sorted(
            {item.station_standard for item in connectors},
            key=lambda item: STATION_ORDER.index(item) if item in STATION_ORDER else 99,
        )
    )
    current_types = {item.current_type for item in connectors}
    no_dc = _flag(row.get("noDcDeclared")) or "DC" not in current_types

    limit_kw, limit_kind = _parse_charge_limit(row.get("chargeLimit") or "")
    ac_limit = limit_kw if limit_kind == "AC" else None
    dc_limit = limit_kw if limit_kind == "DC" else None
    warnings: list[str] = []
    if limit_kw is not None and limit_kind is None:
        if current_types == {"DC"}:
            dc_limit = limit_kw
        elif current_types == {"AC"}:
            ac_limit = limit_kw
        else:
            warnings.append("توان شارژ در منبع هست، اما AC یا DC بودن آن مشخص نیست.")

    powertrain = (row.get("evCarType") or "").strip().upper()
    if powertrain not in POWERTRAIN_LABELS:
        powertrain = "BEV"
        warnings.append("نوع قوای محرکه در منبع نامشخص است.")

    importer_raw, importer_notes = _split_importer(row.get("importer") or "")
    importer_key = re.sub(r"\s+", " ", (importer_raw or "").casefold())
    importer_fa, _importer_slug = IMPORTERS.get(importer_key, (importer_raw, None))

    status = "source_only"
    if importer_notes and "متفاوت" in importer_notes:
        warnings.append("بسته به واردکننده، درگاه شارژ ممکن است فرق کند.")
        status = "needs_review"
    if powertrain == "HEV" and (connectors or _number(row.get("batteryKwhMax"))):
        warnings.append("منبع این خودرو را هیبرید ثبت کرده، اما ظرفیت باتری و درگاه شارژ دارد.")
        status = "needs_review"
    if powertrain == "BEV" and no_dc:
        warnings.append("برای این خودروی برقی ورودی شارژ سریع DC اعلام نشده.")
        status = "needs_review"
    elif no_dc:
        warnings.append("ورودی شارژ سریع DC در منبع اعلام نشده.")
    if "AC" not in current_types and connectors:
        warnings.append("ورودی شارژ AC در منبع اعلام نشده.")

    battery_min = _number(row.get("batteryKwhMin"))
    battery_max = _number(row.get("batteryKwhMax"))
    variant_name = str(model_year) if model_year else "Default"
    display = f"{make_fa} {model_name}"
    if model_year:
        display = f"{display} {model_year}"

    aliases = [
        make_en,
        make_fa,
        *extra_aliases,
        model_name,
        raw_model,
        row.get("brand") or "",
        row.get("model") or "",
        display,
        importer_raw or "",
        importer_fa or "",
        variant_name if model_year else "",
    ]
    return make_slug, VehicleVariant(
        id=_variant_id(row["id"]),
        model_slug=model_slug,
        model_name=model_name,
        variant_name=variant_name,
        display_name=display,
        model_year=model_year,
        powertrain_type=powertrain,
        powertrain_label=POWERTRAIN_LABELS[powertrain],
        battery_kwh_min=battery_min,
        battery_kwh_max=battery_max,
        range_km=_number(row.get("rangeKm")),
        range_standard=(row.get("rangeStandard") or "").strip() or None,
        ac_charge_limit_kw=ac_limit,
        dc_charge_limit_kw=dc_limit,
        connectors=connectors,
        station_standards=station_standards,
        importer_name=importer_raw,
        importer_name_fa=importer_fa,
        verification_status=status,
        warnings=tuple(warnings),
        no_dc_declared=no_dc,
        search=_search_blob(aliases),
        source_external_id=row["id"],
    )


def load_catalog(path: Path | None = None) -> VehicleCatalog:
    source = path or DATASET_PATH
    grouped: dict[str, dict[str, list[VehicleVariant]]] = {}
    with source.open(newline="", encoding="utf-8") as handle:
        for row in csv.DictReader(handle):
            if not (row.get("id") or "").strip():
                continue
            make_slug, variant = _row_to_variant(row)
            grouped.setdefault(make_slug, {}).setdefault(variant.model_slug, []).append(variant)

    makes: list[VehicleMake] = []
    for slug, models in grouped.items():
        name_en, name_fa, icon, _aliases = MAKES[slug]
        model_rows = tuple(
            VehicleModel(slug=model_slug, name=variants[0].model_name, variants=tuple(variants))
            for model_slug, variants in sorted(models.items(), key=lambda item: item[1][0].model_name.casefold())
        )
        makes.append(VehicleMake(slug=slug, name_en=name_en, name_fa=name_fa, icon=icon, models=model_rows))
    makes.sort(key=lambda item: item.name_fa)
    return VehicleCatalog(makes=tuple(makes))


@lru_cache(maxsize=1)
def get_catalog() -> VehicleCatalog:
    return load_catalog()
