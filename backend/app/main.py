import logging
import uuid
from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, Response
from sqlalchemy.orm import Session

from app.api.errors import AppError
from app.api.v1.router import router as v1_router
from app.core.config import settings
from app.core.db import get_db, session_scope
from app.ingestion.seed import ensure_sources
from app.services.locations import published_station_entries
from app.services.sitemap import render_sitemap

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")


@asynccontextmanager
async def lifespan(_app: FastAPI):
    with session_scope() as session:
        ensure_sources(session)
    yield


app = FastAPI(
    title="EV98 Charging Platform",
    version="0.1.0",
    summary="نقشه و ingestion چندمنبعی ایستگاه‌های شارژ",
    lifespan=lifespan,
)
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origin_list,
    allow_methods=["*"],
    allow_headers=["*"],
    expose_headers=["X-Request-Id"],
)
app.include_router(v1_router, prefix="/v1")


@app.middleware("http")
async def request_id(request: Request, call_next):
    incoming = request.headers.get("x-request-id") or str(uuid.uuid4())
    response = await call_next(request)
    response.headers["X-Request-Id"] = incoming
    return response


@app.exception_handler(AppError)
async def app_error(_request: Request, exc: AppError) -> JSONResponse:
    return JSONResponse(
        status_code=exc.status_code,
        content={"type": "about:blank", "title": exc.title, "status": exc.status_code, "detail": exc.detail},
    )


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/sitemap.xml", include_in_schema=False)
def sitemap(db: Session = Depends(get_db)) -> Response:
    xml = render_sitemap(settings.public_site_url, published_station_entries(db))
    return Response(content=xml, media_type="application/xml", headers={"Cache-Control": "public, max-age=3600"})
