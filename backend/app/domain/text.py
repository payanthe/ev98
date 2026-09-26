import math
import re

_ARABIC_CHARS = str.maketrans(
    {
        "ي": "ی",
        "ك": "ک",
        "ة": "ه",
        "أ": "ا",
        "إ": "ا",
        "آ": "ا",
        "ؤ": "و",
        "ئ": "ی",
    }
)
_STATION_PREFIXES = (
    "ایستگاه شارژ مپنا - ",
    "ایستگاه شارژ مپنا-",
    "ایستگاه شارژ ",
    "ایستگاه ",
)


def normalize_fa(value: str | None, *, cluster_key: bool = False) -> str:
    if not value:
        return ""
    text = value.translate(_ARABIC_CHARS)
    text = text.replace("\u200c", " ")
    text = text.replace("ـ", "")
    text = re.sub(r"\s+", " ", text).strip().casefold()
    if cluster_key:
        for prefix in _STATION_PREFIXES:
            normalized_prefix = prefix.translate(_ARABIC_CHARS).replace("\u200c", " ").casefold()
            if text.startswith(normalized_prefix):
                text = text[len(normalized_prefix) :].strip()
                break
    return text


def haversine_m(lat1: float, lng1: float, lat2: float, lng2: float) -> float:
    radius = 6_371_000.0
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    d_phi = math.radians(lat2 - lat1)
    d_lambda = math.radians(lng2 - lng1)
    a = math.sin(d_phi / 2) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(d_lambda / 2) ** 2
    return 2 * radius * math.asin(math.sqrt(a))


def split_fa_list(value: str | None) -> list[str]:
    if not value:
        return []
    parts = re.split(r"[،,;/|]", value)
    return [part.strip() for part in parts if part.strip()]


def kw_to_watts(value: object) -> int | None:
    if value is None or value == "":
        return None
    try:
        number = float(value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return None
    if number <= 0:
        return None
    if number > 1000:
        return int(round(number))
    return int(round(number * 1000))


def toman_to_rial(toman: int) -> int:
    return int(toman) * 10
