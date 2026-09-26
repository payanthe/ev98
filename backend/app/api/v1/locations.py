from uuid import UUID

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.api.errors import AppError
from app.core.db import get_db
from app.schemas.api import LocationDetail, MapResponse
from app.services.locations import get_location, search_locations

router = APIRouter(prefix="/locations", tags=["locations"])


def _bbox(value: str | None) -> tuple[float, float, float, float] | None:
    if not value:
        return None
    parts = [part.strip() for part in value.split(",")]
    if len(parts) != 4:
        raise AppError(400, "Invalid bbox", "bbox باید به شکل south,west,north,east باشد.")
    try:
        south, west, north, east = (float(part) for part in parts)
    except ValueError as exc:
        raise AppError(400, "Invalid bbox", "مختصات محدوده عدد نیست.") from exc
    if not (-90 <= south < north <= 90 and -180 <= west < east <= 180):
        raise AppError(400, "Invalid bbox", "مختصات محدوده نامعتبر است.")
    return south, west, north, east


@router.get("/", response_model=MapResponse)
def list_locations(
    bbox: str | None = None,
    lat: float | None = None,
    lng: float | None = None,
    radius_m: int | None = Query(default=None, ge=100, le=100_000),
    q: str | None = Query(default=None, max_length=80),
    connector: list[str] = Query(default=[]),
    min_power_kw: float | None = Query(default=None, ge=0, le=1000),
    source: list[str] = Query(default=[]),
    availability: str | None = Query(default=None, pattern="^(available|charging|unavailable|stale|operational|unknown)$"),
    limit: int = Query(default=800, ge=1, le=1000),
    db: Session = Depends(get_db),
) -> MapResponse:
    box = _bbox(bbox)
    has_nearby = lat is not None or lng is not None or radius_m is not None
    if has_nearby and (lat is None or lng is None):
        raise AppError(400, "Invalid nearby", "جست‌وجوی نزدیک به lat و lng نیاز دارد.")
    if lat is not None and not -90 <= lat <= 90:
        raise AppError(400, "Invalid nearby", "عرض جغرافیایی نامعتبر است.")
    if lng is not None and not -180 <= lng <= 180:
        raise AppError(400, "Invalid nearby", "طول جغرافیایی نامعتبر است.")
    if box is None and not has_nearby and not q:
        raise AppError(400, "Missing query", "bbox، مختصات نزدیک، یا عبارت جست‌وجو لازم است.")
    south = west = north = east = None
    if box:
        south, west, north, east = box
    return search_locations(
        db,
        south=south,
        west=west,
        north=north,
        east=east,
        lat=lat,
        lng=lng,
        radius_m=radius_m or (5_000 if has_nearby else None),
        q=q,
        connectors=connector,
        min_power_kw=min_power_kw,
        sources=source,
        availability=availability,
        limit=limit,
    )


@router.get("/{location_id}", response_model=LocationDetail)
def read_location(location_id: UUID, db: Session = Depends(get_db)) -> LocationDetail:
    detail = get_location(db, location_id)
    if detail is None:
        raise AppError(404, "Not found", "ایستگاه پیدا نشد.")
    return detail
