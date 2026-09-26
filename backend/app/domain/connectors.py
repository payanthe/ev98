OCM_CONNECTION_IDS: dict[int, tuple[str, str | None, str | None]] = {
    1: ("TYPE_1", "AC", "CABLE"),
    2: ("CHADEMO", "DC", "CABLE"),
    25: ("TYPE_2", "AC", "SOCKET"),
    27: ("NACS", "DC", "CABLE"),
    30: ("NACS", "DC", "CABLE"),
    32: ("CCS_1", "DC", "CABLE"),
    33: ("CCS_2", "DC", "CABLE"),
    1036: ("TYPE_2", "AC", "CABLE"),
    1038: ("GBT_AC", "AC", "SOCKET"),
    1039: ("GBT_AC", "AC", "CABLE"),
    1040: ("GBT_DC", "DC", "CABLE"),
}

OCM_CURRENT = {10: "AC_1_PHASE", 20: "AC_3_PHASE", 30: "DC"}


def map_connector_title(title: str | None) -> tuple[str, str | None, str | None] | None:
    if not title:
        return None
    text = title.upper().replace(" ", "").replace("_", "").replace("-", "")
    if "CCS" in text and ("TYPE2" in text or "CCS2" in text or text.endswith("2")):
        return "CCS_2", "DC", "CABLE"
    if "CCS" in text and "TYPE1" in text:
        return "CCS_1", "DC", "CABLE"
    if "CHADEMO" in text:
        return "CHADEMO", "DC", "CABLE"
    if "GBT" in text or "GB/T" in title.upper():
        if "AC" in text:
            return "GBT_AC", "AC", "SOCKET"
        return "GBT_DC", "DC", "CABLE"
    if "NACS" in text or "TESLA" in text:
        return "NACS", "DC", "CABLE"
    if "TYPE2" in text or "TYPE 2" in title.upper():
        cable = "CABLE" if "TETHER" in text or "CABLE" in text else "SOCKET"
        return "TYPE_2", "AC", cable
    if "TYPE1" in text or "J1772" in text:
        return "TYPE_1", "AC", "CABLE"
    return None


def map_sharinet_connector(name: str | None, connector_type: str | None) -> tuple[str, str | None, str | None]:
    raw = name or ""
    compact = raw.upper().replace(" ", "").replace("_", "")
    power_type = None
    if (connector_type or "").upper() == "DC" or "-DC-" in compact or "DC" in compact:
        power_type = "DC"
    elif (connector_type or "").upper() == "AC" or "-AC-" in compact:
        power_type = "AC"

    if "CCS2" in compact or "CCS-2" in raw.upper():
        return "CCS_2", power_type or "DC", "CABLE"
    if "CCS1" in compact:
        return "CCS_1", power_type or "DC", "CABLE"
    if "CHADEMO" in compact:
        return "CHADEMO", "DC", "CABLE"
    if "GB/T" in raw.upper() or "GBT" in compact:
        if power_type == "AC":
            return "GBT_AC", "AC", "SOCKET"
        return "GBT_DC", "DC", "CABLE"
    if "TYPE2" in compact or "TYPE-2" in raw.upper():
        return "TYPE_2", power_type or "AC", "SOCKET"
    if "TYPE1" in compact:
        return "TYPE_1", power_type or "AC", "CABLE"
    if "NACS" in compact or "TESLA" in compact:
        return "NACS", power_type, "CABLE"
    return "UNKNOWN", power_type, None


def map_abrp_standard(standard: str | None, power_w: int | None) -> tuple[str, str | None, str | None]:
    key = (standard or "").upper().replace(" ", "").replace("_", "").replace("-", "")
    if key in {"TYPE2", "TYPE2SOCKET"}:
        return "TYPE_2", "AC", "SOCKET"
    if key in {"TYPE2CABLE", "TYPE2TETHERED"}:
        return "TYPE_2", "AC", "CABLE"
    if key == "TYPE1":
        return "TYPE_1", "AC", "CABLE"
    if key in {"CCS", "CCS2"}:
        return "CCS_2", "DC", "CABLE"
    if key == "CCS1":
        return "CCS_1", "DC", "CABLE"
    if key == "CHADEMO":
        return "CHADEMO", "DC", "CABLE"
    if key in {"GBT", "GBTAC", "GBTDC"}:
        if key == "GBTAC" or (key == "GBT" and (power_w or 0) < 20_000):
            return "GBT_AC", "AC", "SOCKET"
        return "GBT_DC", "DC", "CABLE"
    if key in {"NACS", "TESLA"}:
        return "NACS", "DC", "CABLE"
    return "UNKNOWN", None, None


def power_family(power_type: str | None) -> str | None:
    if not power_type:
        return None
    if power_type == "DC":
        return "DC"
    if power_type.startswith("AC"):
        return "AC"
    return power_type
