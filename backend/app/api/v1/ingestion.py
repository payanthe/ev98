import secrets

from fastapi import APIRouter, BackgroundTasks, Depends, Request
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.errors import AppError
from app.core.config import settings
from app.core.db import get_db
from app.ingestion.seed import ensure_sources
from app.ingestion.service import SyncConflict, execute_sync, latest_runs, start_sync
from app.models.entities import SourceSystem, SyncRun
from app.schemas.api import SourceStatusOut, SyncRequest, SyncRunOut

router = APIRouter(prefix="/ingestion", tags=["ingestion"])


def _require_token(request: Request) -> None:
    expected = settings.ingestion_token
    if not expected:
        return
    sent = request.headers.get("x-ingestion-token", "")
    if not secrets.compare_digest(sent, expected):
        raise AppError(401, "Unauthorized", "توکن همگام‌سازی معتبر نیست.")


def _run_out(run: SyncRun, source_code: str) -> SyncRunOut:
    return SyncRunOut(
        id=run.id,
        source=source_code,
        status=run.status,
        mode=run.mode,
        started_at=run.started_at,
        finished_at=run.finished_at,
        stats=dict(run.stats or {}),
        error=run.error,
    )


def _configured(code: str) -> bool:
    if code == "sharinet":
        return True
    if code == "ocm":
        return bool(settings.ocm_api_key)
    if code == "abrp":
        return bool(settings.abrp_api_key)
    return False


@router.get("/sources", response_model=list[SourceStatusOut])
def list_sources(db: Session = Depends(get_db)) -> list[SourceStatusOut]:
    ensure_sources(db)
    db.commit()
    runs = latest_runs(db)
    sources = db.scalars(select(SourceSystem).order_by(SourceSystem.code)).all()
    return [
        SourceStatusOut(
            code=source.code,
            name=source.name,
            source_type=source.source_type,
            attribution=source.attribution_text,
            configured=_configured(source.code),
            active=source.active,
            last_run=_run_out(runs[source.code], source.code) if source.code in runs else None,
        )
        for source in sources
    ]


@router.post("/sync", response_model=SyncRunOut, status_code=202)
def sync_source(
    body: SyncRequest,
    request: Request,
    background: BackgroundTasks,
    db: Session = Depends(get_db),
) -> SyncRunOut:
    _require_token(request)
    if body.source == "ocm" and not settings.ocm_api_key:
        raise AppError(400, "Missing API key", "برای Open Charge Map متغیر OCM_API_KEY لازم است.")
    if body.source == "abrp" and not settings.abrp_api_key:
        raise AppError(400, "Missing API key", "برای ABRP متغیر ABRP_API_KEY لازم است.")
    try:
        run = start_sync(db, body.source, body.include_details)
    except SyncConflict as exc:
        raise AppError(409, "Sync already running", exc.message) from exc
    background.add_task(execute_sync, run.id)
    return _run_out(run, body.source)


@router.get("/runs/{run_id}", response_model=SyncRunOut)
def get_run(run_id: str, db: Session = Depends(get_db)) -> SyncRunOut:
    try:
        import uuid

        parsed = uuid.UUID(run_id)
    except ValueError as exc:
        raise AppError(404, "Not found", "اجرای همگام‌سازی پیدا نشد.") from exc
    run = db.get(SyncRun, parsed)
    if run is None:
        raise AppError(404, "Not found", "اجرای همگام‌سازی پیدا نشد.")
    source = db.get(SourceSystem, run.source_system_id)
    return _run_out(run, source.code if source else "")
