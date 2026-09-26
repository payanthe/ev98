from dataclasses import asdict
from uuid import UUID

from fastapi import APIRouter

from app.api.errors import AppError
from app.schemas.vehicles import VehicleCatalogOut, VehicleVariantOut
from app.vehicles.catalog import get_catalog

router = APIRouter(prefix="/vehicles", tags=["vehicles"])


def _catalog() -> VehicleCatalogOut:
    return VehicleCatalogOut.model_validate(asdict(get_catalog()))


@router.get("/", response_model=VehicleCatalogOut)
def list_vehicles() -> VehicleCatalogOut:
    return _catalog()


@router.get("/{variant_id}", response_model=VehicleVariantOut)
def read_vehicle(variant_id: UUID) -> VehicleVariantOut:
    variant = get_catalog().get(str(variant_id))
    if variant is None:
        raise AppError(404, "Not found", "خودرو پیدا نشد.")
    return VehicleVariantOut.model_validate(asdict(variant))
