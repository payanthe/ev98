"""ABRP charger search.

An ABRP charger with source=ocm is the same location as that Open Charge Map POI.
"""

from __future__ import annotations

import re
import uuid

import httpx

from app.domain.connectors import map_abrp_standard
from app.domain.status import ABRP_STATUS, OPERATIONAL, UNKNOWN
from app.ingestion.http import UpstreamError, request_json
from app.ingestion.records import NormalizedConnector, NormalizedEvse, NormalizedRecord

ATTRIBUTION = "داده از ABRP / Iternio. رکوردهای source=ocm به Open Charge Map وصل می‌شوند."


def parse_ocm_id(item: dict) -> str | None:
    url = str(item.get("editableUrl") or "")
    match = re.search(r"/poi/(?:edit|details)/(\d+)", url)
    source = item.get("source")
    if match and (source in (None, "ocm") or "openchargemap.org" in url):
        if source == "ocm" or "openchargemap.org" in url:
            return match.group(1)
    if source == "ocm":
        for evse in item.get("evses") or []:
            if not isinstance(evse, dict):
                continue
            external = str(evse.get("id") or "")
            if re.fullmatch(r"\d+\*\d+", external):
                return external.split("*", 1)[0]
    return None


def _dominant_status(item: dict) -> str:
    counts: dict[str, int] = {}
    for group in item.get("evseSummary") or []:
        if not isinstance(group, dict):
            continue
        for entry in group.get("statuses") or []:
            if not isinstance(entry, dict):
                continue
            mapped = ABRP_STATUS.get(str(entry.get("status") or "").upper(), UNKNOWN)
            counts[mapped] = counts.get(mapped, 0) + int(entry.get("count") or 0)
    if not counts:
        return UNKNOWN
    return max(counts, key=counts.get)


def normalize_charger(item: dict) -> NormalizedRecord | None:
    external_id = str(item.get("id") or "").strip()
    coords = item.get("coordinates") if isinstance(item.get("coordinates"), dict) else {}
    lat = coords.get("lat", item.get("lat"))
    lng = coords.get("long", item.get("long"))
    name = item.get("name")
    if not external_id or lat is None or lng is None or not name:
        return None

    dynamic = bool(item.get("hasDynamicStatus"))
    status = _dominant_status(item) if dynamic else OPERATIONAL
    kind = "live" if dynamic else "operational"
    evses_raw = [evse for evse in (item.get("evses") or []) if isinstance(evse, dict)]
    evses: list[NormalizedEvse] = []
    if evses_raw:
        for evse in evses_raw:
            connectors: list[NormalizedConnector] = []
            for index, connector in enumerate(evse.get("connectors") or [], start=1):
                if not isinstance(connector, dict):
                    continue
                power = connector.get("power")
                try:
                    power_w = int(power) if power else None
                except (TypeError, ValueError):
                    power_w = None
                standard, power_type, fmt = map_abrp_standard(connector.get("standard"), power_w)
                connectors.append(
                    NormalizedConnector(
                        index=index,
                        standard=standard,
                        power_type=power_type,
                        format=fmt,
                        max_power_w=power_w,
                        raw_name=connector.get("standard"),
                    )
                )
            powers = [connector.max_power_w for connector in connectors if connector.max_power_w]
            evses.append(
                NormalizedEvse(
                    external_id=str(evse.get("id") or f"{external_id}:{len(evses) + 1}"),
                    status=status,
                    status_kind=kind,
                    connectors=connectors,
                    max_power_w=max(powers) if powers else None,
                    physical_reference=str(evse.get("id") or ""),
                )
            )
    else:
        connectors = []
        for group in item.get("evseSummary") or []:
            if not isinstance(group, dict):
                continue
            count = int(group.get("count") or 1)
            for connector in group.get("connectors") or []:
                if not isinstance(connector, dict):
                    continue
                power = connector.get("power")
                try:
                    power_w = int(power) if power else None
                except (TypeError, ValueError):
                    power_w = None
                standard, power_type, fmt = map_abrp_standard(connector.get("standard"), power_w)
                for _ in range(max(1, min(count, 12))):
                    connectors.append(
                        NormalizedConnector(
                            index=len(connectors) + 1,
                            standard=standard,
                            power_type=power_type,
                            format=fmt,
                            max_power_w=power_w,
                            raw_name=connector.get("standard"),
                        )
                    )
        powers = [connector.max_power_w for connector in connectors if connector.max_power_w]
        evses.append(
            NormalizedEvse(
                external_id=external_id,
                status=status,
                status_kind=kind,
                connectors=connectors,
                max_power_w=max(powers) if powers else None,
            )
        )

    network = item.get("network") if isinstance(item.get("network"), dict) else {}
    accessibility = item.get("accessibility") if isinstance(item.get("accessibility"), dict) else {}
    is_public = None
    access_type = "unknown"
    if str(accessibility.get("status") or "").upper() == "OPEN":
        is_public = True
        access_type = "public"
    return NormalizedRecord(
        source_code="abrp",
        entity_type="location",
        external_id=external_id,
        name=str(name).strip(),
        lat=float(lat),
        lng=float(lng),
        address=item.get("address"),
        operator_name=network.get("name"),
        is_public=is_public,
        access_type=access_type,
        attribution=ATTRIBUTION,
        ocm_external_id=parse_ocm_id(item),
        has_dynamic_status=dynamic,
        detail_fetched=True,
        evses=evses,
        raw=item,
    )


def iran_tiles() -> list[tuple[float, float, float, float]]:
    tiles: list[tuple[float, float, float, float]] = []
    lat = 25.0
    while lat < 40:
        lng = 44.0
        while lng < 63.5:
            tiles.append((lat, lng, min(lat + 3, 40), min(lng + 3.5, 63.5)))
            lng += 3.5
        lat += 3
    return tiles


class AbrpAdapter:
    code = "abrp"

    def __init__(self, api_key: str):
        if not api_key:
            raise UpstreamError(self.code, "ABRP_API_KEY تنظیم نشده است.")
        self.session_id = str(uuid.uuid4())
        self.client = httpx.Client(
            timeout=httpx.Timeout(30.0),
            headers={
                "X-API-KEY": api_key,
                "X-ABRP-VERSION": "7.1.7",
                "Content-Type": "application/json",
                "Accept": "application/json",
                "ACCEPT-LANGUAGE": "fa",
                "User-Agent": "ev98-platform/0.1",
            },
        )

    def close(self) -> None:
        self.client.close()

    def _body(self, payload: dict) -> dict:
        return {**payload, "session_id": self.session_id, "customer_preset": "abrp-android"}

    def fetch_ids(self, south: float, west: float, north: float, east: float) -> list[int]:
        payload = request_json(
            self.client,
            "POST",
            "https://api.iternio.com/2/charger/_search/bounding-boxes/ids",
            source=self.code,
            json=self._body(
                {
                    "boundingBoxes": [
                        {
                            "coordinates": [
                                {"long": east, "lat": south},
                                {"long": west, "lat": north},
                            ]
                        }
                    ],
                    "sortBy": "POWER",
                    "filter": {},
                    "boost": {"reliability": True, "cardIds": [], "networkIds": []},
                }
            ),
        )
        ids: list[int] = []
        for box in (payload or {}).get("items") or []:
            if not isinstance(box, dict):
                continue
            for charger in box.get("chargers") or []:
                if isinstance(charger, dict) and charger.get("id") is not None:
                    ids.append(int(charger["id"]))
        return ids

    def fetch_details(self, ids: list[int]) -> list[dict]:
        items: list[dict] = []
        for start in range(0, len(ids), 20):
            chunk = ids[start : start + 20]
            payload = request_json(
                self.client,
                "POST",
                "https://api.iternio.com/2/charger/_get/details",
                source=self.code,
                json=self._body({"chargerIds": chunk}),
            )
            for entry in (payload or {}).get("items") or []:
                if not isinstance(entry, dict) or entry.get("status") not in (None, "ok"):
                    continue
                item = entry.get("item") or entry
                if isinstance(item, dict) and item.get("id") is not None:
                    items.append(item)
        return items

    def fetch_iran(self) -> tuple[list[dict], list[str]]:
        warnings: list[str] = []
        seen: dict[int, None] = {}
        for south, west, north, east in iran_tiles():
            for charger_id in self.fetch_ids(south, west, north, east):
                seen[charger_id] = None
        if not seen:
            warnings.append("ABRP هیچ شناسه‌ای داخل کاشی‌های ایران برنگرداند.")
        return self.fetch_details(list(seen)), warnings
