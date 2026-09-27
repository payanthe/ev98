"""Open Charge Map Iran POIs.

One POI becomes one location. Connections stay on a single EVSE unless the
payload itself separates charge points; quantity only repeats connectors.
"""

from __future__ import annotations

import httpx

from app.domain.connectors import OCM_CONNECTION_IDS, OCM_CURRENT, map_connector_title
from app.domain.hours import parse_hours
from app.domain.status import OCM_STATUS, REMOVED, UNKNOWN
from app.domain.text import kw_to_watts
from app.ingestion.http import UpstreamError, request_json
from app.ingestion.notes import extract_ocm_annotations
from app.ingestion.records import NormalizedConnector, NormalizedEvse, NormalizedRecord

DELISTED = {250, 1000, 1001, 1002, 1005, 1010, 1020}
PUBLIC_USAGE = {1, 4, 5, 7}
PRIVATE_USAGE = {2, 3, 6}
ATTRIBUTION = "داده از Open Charge Map. مجوز هر ایستگاه تابع ارائه‌دهندهٔ همان رکورد است."


def _nested_title(value) -> str | None:
    if isinstance(value, dict):
        title = value.get("Title") or value.get("title")
        return str(title).strip() if title else None
    return None


def _access(usage_id: object) -> tuple[bool | None, str]:
    try:
        usage = int(usage_id)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return None, "unknown"
    if usage in PUBLIC_USAGE:
        return True, "public"
    if usage in PRIVATE_USAGE:
        return False, "private"
    return None, "unknown"


def _image_urls(poi: dict) -> list[str]:
    """Return enabled OCM photo URLs, excluding videos and unsafe URLs."""
    urls: list[str] = []
    for media in poi.get("MediaItems") or []:
        if not isinstance(media, dict):
            continue
        if media.get("IsEnabled") is False or media.get("IsVideo") is True:
            continue
        url = str(media.get("ItemURL") or "").strip()
        if url.startswith("https://") and url not in urls:
            urls.append(url)
    return urls


def normalize_poi(
    poi: dict,
    operators: dict[int, str] | None = None,
    connection_titles: dict[int, str] | None = None,
) -> NormalizedRecord | None:
    external_id = str(poi.get("ID") or "").strip()
    address = poi.get("AddressInfo") if isinstance(poi.get("AddressInfo"), dict) else {}
    lat = address.get("Latitude")
    lng = address.get("Longitude")
    name = address.get("Title")
    if not external_id or lat is None or lng is None or not name:
        return None

    submission = poi.get("SubmissionStatusTypeID")
    status_id = poi.get("StatusTypeID")
    try:
        status_id_int = int(status_id) if status_id is not None else None
    except (TypeError, ValueError):
        status_id_int = None
    status, status_kind = OCM_STATUS.get(status_id_int, (UNKNOWN, "operational")) if status_id_int is not None else (UNKNOWN, "operational")
    publish = submission not in DELISTED and status != REMOVED

    connectors: list[NormalizedConnector] = []
    index = 1
    for connection in poi.get("Connections") or []:
        if not isinstance(connection, dict):
            continue
        type_id = connection.get("ConnectionTypeID")
        try:
            type_id_int = int(type_id)
        except (TypeError, ValueError):
            type_id_int = None
        mapped = None
        if type_id_int is not None:
            mapped = map_connector_title((connection_titles or {}).get(type_id_int)) or OCM_CONNECTION_IDS.get(type_id_int)
        if mapped is None:
            mapped = map_connector_title(_nested_title(connection.get("ConnectionType")))
        standard, power_type, fmt = mapped or ("UNKNOWN", None, None)
        current_id = connection.get("CurrentTypeID")
        try:
            current = OCM_CURRENT.get(int(current_id))
        except (TypeError, ValueError):
            current = None
        if current:
            power_type = current
        watts = kw_to_watts(connection.get("PowerKW"))
        quantity = connection.get("Quantity") or 1
        try:
            quantity = max(1, min(int(quantity), 12))
        except (TypeError, ValueError):
            quantity = 1
        raw_name = _nested_title(connection.get("ConnectionType"))
        for _ in range(quantity):
            connectors.append(
                NormalizedConnector(
                    index=index,
                    standard=standard,
                    power_type=power_type,
                    format=fmt,
                    max_power_w=watts,
                    raw_name=raw_name,
                )
            )
            index += 1

    operator_name = _nested_title(poi.get("OperatorInfo"))
    if operator_name is None and operators and poi.get("OperatorID") is not None:
        try:
            operator_name = operators.get(int(poi["OperatorID"]))
        except (TypeError, ValueError):
            operator_name = None
    is_public, access_type = _access(poi.get("UsageTypeID"))
    number_of_points = poi.get("NumberOfPoints")
    try:
        number_of_points = int(number_of_points) if number_of_points else None
    except (TypeError, ValueError):
        number_of_points = None
    powers = [item.max_power_w for item in connectors if item.max_power_w]
    provider = _nested_title(poi.get("DataProvider"))
    attribution = ATTRIBUTION if not provider else f"{ATTRIBUTION} ارائه‌دهنده: {provider}."
    annotations = extract_ocm_annotations(poi)
    hours = parse_hours(annotations.hours_summary, is_24_7=annotations.is_24_7)

    return NormalizedRecord(
        source_code="ocm",
        entity_type="location",
        external_id=external_id,
        name=str(name).strip(),
        lat=float(lat),
        lng=float(lng),
        address=address.get("AddressLine1"),
        city=address.get("Town"),
        province=address.get("StateOrProvince"),
        operator_name=operator_name,
        phone=address.get("ContactTelephone1"),
        website=address.get("RelatedURL"),
        is_public=is_public,
        is_24_7=True if hours.is_24_7 else annotations.is_24_7,
        hours_summary=annotations.hours_summary,
        hours_schedule=hours.as_dict() if hours.parseable or hours.raw else None,
        access_type=access_type,
        facilities=list(annotations.facilities or []),
        image_urls=_image_urls(poi),
        notes=annotations.notes,
        attribution=attribution,
        publish=publish,
        detail_fetched=True,
        evses=[
            NormalizedEvse(
                external_id=external_id,
                status=status if publish else REMOVED,
                status_kind=status_kind if status_kind == "live" else "operational",
                connectors=connectors,
                max_power_w=max(powers) if powers else None,
                counts={"total": number_of_points} if number_of_points else None,
                physical_reference=f"OCM {external_id}",
            )
        ],
        raw=poi,
    )


class OcmAdapter:
    code = "ocm"

    def __init__(self, api_key: str):
        if not api_key:
            raise UpstreamError(self.code, "OCM_API_KEY تنظیم نشده است.")
        self.client = httpx.Client(
            timeout=httpx.Timeout(40.0),
            headers={
                "X-API-Key": api_key,
                "User-Agent": "ev98-platform/0.1",
                "Accept": "application/json",
            },
        )
        self.operators: dict[int, str] = {}
        self.connection_titles: dict[int, str] = {}

    def close(self) -> None:
        self.client.close()

    def load_reference(self) -> None:
        try:
            payload = request_json(
                self.client,
                "GET",
                "https://api.openchargemap.io/v3/referencedata/",
                source=self.code,
                retries=2,
            )
        except UpstreamError:
            return
        if not isinstance(payload, dict):
            return
        for item in payload.get("Operators") or []:
            if isinstance(item, dict) and item.get("ID") and item.get("Title"):
                self.operators[int(item["ID"])] = str(item["Title"])
        for item in payload.get("ConnectionTypes") or []:
            if isinstance(item, dict) and item.get("ID") and item.get("Title"):
                self.connection_titles[int(item["ID"])] = str(item["Title"])

    def fetch_iran(self) -> list[dict]:
        payload = request_json(
            self.client,
            "GET",
            "https://api.openchargemap.io/v3/poi/",
            source=self.code,
            params={
                "output": "json",
                "compact": "false",
                "verbose": "false",
                "countrycode": "IR",
                "maxresults": "2000",
                "client": "ev98.platform",
            },
        )
        if not isinstance(payload, list):
            raise UpstreamError(self.code, "پاسخ Open Charge Map آرایه نیست.")
        return payload

    def normalize_all(self, pois: list[dict]) -> tuple[list[NormalizedRecord], list[str], list[str]]:
        records: list[NormalizedRecord] = []
        dropped: list[str] = []
        warnings: list[str] = []
        if len(pois) >= 2000:
            warnings.append("OCM maxresults پر شد؛ ممکن است بخشی از ایران جا مانده باشد.")
        for poi in pois:
            external_id = str(poi.get("ID") or "")
            record = normalize_poi(poi, self.operators, self.connection_titles)
            if record is None:
                if external_id:
                    dropped.append(external_id)
                continue
            records.append(record)
        return records, dropped, warnings
