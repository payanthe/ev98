from fastapi import APIRouter

from app.api.v1 import ingestion, locations, vehicles

router = APIRouter()
router.include_router(locations.router)
router.include_router(vehicles.router)
router.include_router(ingestion.router)
