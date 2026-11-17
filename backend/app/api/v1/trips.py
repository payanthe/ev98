from uuid import UUID

from fastapi import APIRouter, Depends, Query
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.api.errors import AppError
from app.core.config import settings
from app.core.db import get_db
from app.services.trip_places import reverse_place, search_places
from app.services.trip_planner import plan_trip
from app.services.trip_router import Point, require_graph

router = APIRouter(prefix="/trips", tags=["trips"])


class TripRequest(BaseModel):
    origin_lat: float = Field(ge=-90, le=90)
    origin_lng: float = Field(ge=-180, le=180)
    destination_lat: float = Field(ge=-90, le=90)
    destination_lng: float = Field(ge=-180, le=180)
    vehicle_id: UUID
    start_soc: float = Field(ge=1, le=100)
    include_grade: bool = True


@router.get("/places")
def places(q: str = Query(min_length=3, max_length=100)) -> list[dict]:
    return search_places(q)


@router.get("/reverse")
def reverse(lat: float = Query(ge=-90, le=90), lng: float = Query(ge=-180, le=180)) -> dict:
    return reverse_place(Point(lat, lng))


@router.post("/plan")
def plan(payload: TripRequest, db: Session = Depends(get_db)) -> dict:
    return plan_trip(db, Point(payload.origin_lat, payload.origin_lng), Point(payload.destination_lat, payload.destination_lng), str(payload.vehicle_id), payload.start_soc,
                     include_grade=payload.include_grade)


@router.api_route("/map/iran.pmtiles", methods=["GET", "HEAD"], include_in_schema=False)
def map_archive() -> FileResponse:
    archive = settings.offline_trip_dir / "iran.pmtiles"
    try:
        with archive.open("rb") as file:
            ready = file.read(8) == b"PMTiles\x03"
    except OSError:
        ready = False
    if not ready:
        raise AppError(503, "Map archive unavailable", "نقشهٔ پایهٔ آفلاین آماده نیست.")
    return FileResponse(archive, media_type="application/vnd.pmtiles",
                        headers={"Cache-Control": "public, max-age=3600"})


@router.get("/ready", include_in_schema=False)
def trip_ready() -> dict[str, str]:
    map_archive()
    search_places("تهران")
    require_graph(settings.offline_trip_dir / "valhalla_tiles")
    return {"status": "ok"}
