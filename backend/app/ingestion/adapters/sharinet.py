"""Sharinet public charger inventory.

Each list row is a charge point, not a location. The pipeline clusters them.
"""

from __future__ import annotations

import threading
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime

import httpx

from app.domain.connectors import map_sharinet_connector
from app.domain.hours import parse_hours
from app.domain.status import derive_sharinet_status, map_sharinet_charger_status, map_sharinet_connector_status
from app.domain.text import kw_to_watts, split_fa_list
from app.ingestion.http import UpstreamError, request_json
from app.ingestion.records import NormalizedConnector, NormalizedEvse, NormalizedRecord

ATTRIBUTION = "دادهٔ ایستگاه، کانکتور و وضعیت از شارینت (مپنا)."


def _unwrap(body: dict) -> dict:
    if not isinstance(body, dict) or body.get("status") != "result":
        raise UpstreamError("sharinet", "پاسخ شارینت envelope معتبر ندارد.")
    result = body.get("result") or {}
    data = result.get("data")
    if not isinstance(data, dict):
        raise UpstreamError("sharinet", "پاسخ شارینت data ندارد.")
    return data


def _parse_time(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value)
    except ValueError:
        return None


def _hours_fields(work_days: str | None, work_hours: str | None) -> tuple[bool | None, str | None, dict | None]:
    if not (work_days or "").strip() and not (work_hours or "").strip():
        return None, None, None
    schedule = parse_hours(work_days=work_days, work_hours=work_hours)
    summary = schedule.raw
    is_24_7 = True if schedule.is_24_7 else (False if schedule.parseable else None)
    return is_24_7, summary, schedule.as_dict() if schedule.parseable or schedule.raw else None


def _guess_region(address: str | None) -> tuple[str | None, str | None]:
    if not address:
        return None, None
    parts = [part.strip() for part in address.split("،") if part.strip()]
    if len(parts) >= 2:
        return parts[0], parts[1]
    if len(parts) == 1:
        return None, parts[0]
    return None, None


def normalize_charge_point(list_item: dict, detail: dict | None) -> NormalizedRecord | None:
    external_id = str(list_item.get("id") or "").strip()
    coords = list_item.get("chargerCoordinates") or {}
    lat = coords.get("lat")
    lng = coords.get("lon")
    if detail and (lat is None or lng is None):
        raw_coords = detail.get("coordinates") or []
        if isinstance(raw_coords, list) and len(raw_coords) >= 2:
            lat, lng = raw_coords[0], raw_coords[1]
    name = (detail or {}).get("name") or list_item.get("stationName")
    if not external_id or lat is None or lng is None or not name:
        return None

    counts = list_item.get("connectorsCount") if isinstance(list_item.get("connectorsCount"), dict) else None
    connectors: list[NormalizedConnector] = []
    if detail and isinstance(detail.get("connectors"), list):
        for offset, item in enumerate(detail["connectors"], start=1):
            standard, power_type, fmt = map_sharinet_connector(
                item.get("connectorName"), item.get("connectorType")
            )
            index = item.get("id")
            try:
                index = int(index)
            except (TypeError, ValueError):
                index = offset
            connectors.append(
                NormalizedConnector(
                    index=index,
                    standard=standard,
                    power_type=power_type,
                    format=fmt,
                    max_power_w=kw_to_watts(item.get("power") or detail.get("power")),
                    status=map_sharinet_connector_status(item.get("status"), item.get("statusCode")),
                    raw_name=item.get("connectorName"),
                )
            )

    connector_statuses = [item.status for item in connectors]
    status = derive_sharinet_status(list_item.get("chargerStatus"), counts, connector_statuses)
    reported = map_sharinet_charger_status(list_item.get("chargerStatus"))
    max_power_w = kw_to_watts((detail or {}).get("power"))
    if max_power_w is None and connectors:
        powers = [item.max_power_w for item in connectors if item.max_power_w]
        max_power_w = max(powers) if powers else None

    province, city = _guess_region((detail or {}).get("address"))
    work_days = (detail or {}).get("workDays")
    work_hours = (detail or {}).get("workHours")
    is_24_7, hours_summary, hours_schedule = _hours_fields(work_days, work_hours)
    plan = (detail or {}).get("plan") if isinstance((detail or {}).get("plan"), dict) else {}
    price = plan.get("cost")
    try:
        price_toman = int(price) if price is not None else None
    except (TypeError, ValueError):
        price_toman = None
    images = []
    for image in (detail or {}).get("images") or []:
        if isinstance(image, dict) and str(image.get("data_url") or "").startswith("https://"):
            images.append(image["data_url"])

    reservable = str(list_item.get("reservable") or "") == "1" or bool((detail or {}).get("reserveNow"))
    return NormalizedRecord(
        source_code="sharinet",
        entity_type="charge_point",
        external_id=external_id,
        name=str(name).strip(),
        lat=float(lat),
        lng=float(lng),
        address=(detail or {}).get("address"),
        city=city,
        province=province,
        operator_name="شارینت",
        is_public=True,
        is_24_7=is_24_7,
        hours_summary=hours_summary,
        hours_schedule=hours_schedule,
        access_type="public",
        facilities=split_fa_list((detail or {}).get("facilities")),
        image_urls=images,
        attribution=ATTRIBUTION,
        price_toman_per_kwh=0 if (detail or {}).get("isFree") else price_toman,
        price_label=(plan.get("timeTypeLable") or plan.get("timeType")) if plan else None,
        price_observed_at=_parse_time(plan.get("time")) if plan else None,
        is_free=bool((detail or {}).get("isFree")),
        is_reservable=reservable,
        detail_fetched=detail is not None,
        evses=[
            NormalizedEvse(
                external_id=external_id,
                status=status,
                status_kind="live",
                connectors=connectors,
                max_power_w=max_power_w,
                reported_status=reported,
                counts=counts,
                physical_reference=str(external_id),
            )
        ],
        raw={"list": list_item, "detail": detail},
    )


class SharinetAdapter:
    code = "sharinet"

    def __init__(self, base_url: str):
        self.base_url = base_url.rstrip("/")
        self.client = httpx.Client(
            timeout=httpx.Timeout(25.0),
            headers={
                "Content-Type": "application/json",
                "Accept": "application/json",
                "Accept-Language": "fa",
                "User-Agent": "ev98-platform/0.1",
            },
        )

    def close(self) -> None:
        self.client.close()

    def fetch_list(self) -> list[dict]:
        body = request_json(
            self.client,
            "POST",
            f"{self.base_url}/api/charger/filter/v2",
            source=self.code,
            json={"defaultFlag": "first", "filters": []},
        )
        chargers = _unwrap(body).get("chargers")
        if not isinstance(chargers, list):
            raise UpstreamError(self.code, "فهرست شارژرها در پاسخ شارینت نیست.")
        return chargers

    def fetch_detail(self, charger_id: str) -> dict:
        body = request_json(
            self.client,
            "POST",
            f"{self.base_url}/api/charger/filter/v2/getStation",
            source=self.code,
            json={"id": charger_id},
        )
        info = _unwrap(body).get("stationInfo")
        if not isinstance(info, dict):
            raise UpstreamError(self.code, f"جزئیات {charger_id} در پاسخ شارینت نیست.")
        return info

    def fetch_details(self, ids: list[str], on_progress=None) -> tuple[dict[str, dict], int]:
        found: dict[str, dict] = {}
        failed = 0
        done = 0
        lock = threading.Lock()

        def work(charger_id: str) -> None:
            nonlocal failed, done
            try:
                info = self.fetch_detail(charger_id)
                with lock:
                    found[charger_id] = info
            except Exception:
                with lock:
                    failed += 1
            finally:
                with lock:
                    done += 1
                    current = done
                    current_failed = failed
                if on_progress and (current % 20 == 0 or current == len(ids)):
                    on_progress(current, current_failed)

        with ThreadPoolExecutor(max_workers=8) as pool:
            list(pool.map(work, ids))
        return found, failed
