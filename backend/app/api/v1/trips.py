from uuid import UUID

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.core.db import get_db
from app.services.trip_planner import Point, plan_trip, reverse_place, search_places

router = APIRouter(prefix="/trips", tags=["trips"])


class TripRequest(BaseModel):
    origin_lat: float = Field(ge=-90, le=90)
    origin_lng: float = Field(ge=-180, le=180)
    destination_lat: float = Field(ge=-90, le=90)
    destination_lng: float = Field(ge=-180, le=180)
    vehicle_id: UUID
    start_soc: float = Field(ge=1, le=100)


@router.get("/places")
def places(q: str = Query(min_length=3, max_length=100)) -> list[dict]:
    return search_places(q)


@router.get("/reverse")
def reverse(lat: float = Query(ge=-90, le=90), lng: float = Query(ge=-180, le=180)) -> dict:
    return reverse_place(Point(lat, lng))


@router.post("/plan")
def plan(payload: TripRequest, db: Session = Depends(get_db)) -> dict:
    return plan_trip(db, Point(payload.origin_lat, payload.origin_lng), Point(payload.destination_lat, payload.destination_lng), str(payload.vehicle_id), payload.start_soc)
