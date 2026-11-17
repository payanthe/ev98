"""Persian place-name normalization shared with the OSM index builder."""
import re

_TRANSLATE = str.maketrans("يكىۀةأإؤ‌۰۱۲۳۴۵۶۷۸۹٠١٢٣٤٥٦٧٨٩", "یکیههائو 01234567890123456789")
_TOKENS = re.compile(r"[^\W_]+", re.UNICODE)


def place_tokens(value: str) -> list[str]:
    return _TOKENS.findall(value.translate(_TRANSLATE).casefold())
