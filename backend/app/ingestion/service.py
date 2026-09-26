"""Source sync orchestration.

Adapters stay network-only. This module clusters, resolves, and commits.
"""

from __future__ import annotations

import logging
import uuid
from datetime import timedelta

from sqlalchemy import select
from app.core.config import settings
from app.core.db import session_scope
from app.ingestion.adapters.abrp import AbrpAdapter, normalize_charger
from app.ingestion.adapters.ocm import OcmAdapter
from app.ingestion.adapters.sharinet import SharinetAdapter, normalize_charge_point
from app.ingestion.cluster import cluster_charge_points
from app.ingestion.persist import (
    get_source,
    hide_empty_locations,
    persist_catalog_record,
    persist_sharinet_cluster,
    withdraw_missing_charge_points,
    withdraw_missing_locations,
)
from app.ingestion.seed import ensure_sources
from app.models.base import utcnow
from app.models.entities import SourceSystem, SyncRun

logger = logging.getLogger("ev98.ingestion")


class SyncConflict(Exception):
    def __init__(self, message: str):
        super().__init__(message)
        self.message = message


def patch_stats(run_id: uuid.UUID, **stats) -> None:
    with session_scope() as session:
        run = session.get(SyncRun, run_id)
        if run is None:
            return
        merged = dict(run.stats or {})
        merged.update(stats)
        run.stats = merged


def mark_failed(run_id: uuid.UUID, exc: Exception) -> None:
    with session_scope() as session:
        run = session.get(SyncRun, run_id)
        if run is None or run.status == "succeeded":
            return
        run.status = "failed"
        run.error = str(exc)[:2000]
        run.finished_at = utcnow()


def start_sync(session, source_code: str, include_details: bool) -> SyncRun:
    ensure_sources(session)
    session.flush()
    source = get_source(session, source_code)
    cutoff = utcnow() - timedelta(minutes=45)
    stale = session.scalars(
        select(SyncRun).where(
            SyncRun.source_system_id == source.id,
            SyncRun.status.in_(("pending", "running")),
            SyncRun.started_at < cutoff,
        )
    ).all()
    for run in stale:
        run.status = "failed"
        run.error = "مهلت اجرا تمام شد."
        run.finished_at = utcnow()
    active = session.scalar(
        select(SyncRun).where(
            SyncRun.source_system_id == source.id,
            SyncRun.status.in_(("pending", "running")),
        )
    )
    if active is not None:
        raise SyncConflict("یک همگام‌سازی برای این منبع در حال اجراست.")
    run = SyncRun(
        source_system_id=source.id,
        status="pending",
        mode="details" if include_details else "inventory",
        stats={"phase": "queued", "source": source_code},
    )
    session.add(run)
    session.commit()
    session.refresh(run)
    return run


def execute_sync(run_id: uuid.UUID) -> None:
    try:
        with session_scope() as session:
            run = session.get(SyncRun, run_id)
            if run is None:
                return
            source = session.get(SourceSystem, run.source_system_id)
            if source is None:
                raise RuntimeError("source missing")
            run.status = "running"
            code = source.code
            include_details = run.mode == "details"
        if code == "sharinet":
            _run_sharinet(run_id, include_details)
        elif code == "ocm":
            _run_ocm(run_id)
        elif code == "abrp":
            _run_abrp(run_id)
        else:
            raise RuntimeError(f"unknown source {code}")
    except Exception as exc:
        logger.exception("sync %s failed", run_id)
        mark_failed(run_id, exc)


def _finish(run_id: uuid.UUID, **stats) -> None:
    with session_scope() as session:
        run = session.get(SyncRun, run_id)
        if run is None:
            return
        merged = dict(run.stats or {})
        merged.update(stats)
        merged["phase"] = "done"
        run.stats = merged
        run.status = "succeeded"
        run.finished_at = utcnow()
        run.error = None


def _run_sharinet(run_id: uuid.UUID, include_details: bool) -> None:
    adapter = SharinetAdapter(settings.sharinet_base_url)
    try:
        patch_stats(run_id, phase="inventory")
        listed = adapter.fetch_list()
        details: dict = {}
        detail_failed = 0
        if include_details:
            patch_stats(run_id, phase="details", listed=len(listed), details_done=0)

            def on_progress(done: int, failed: int) -> None:
                patch_stats(run_id, phase="details", listed=len(listed), details_done=done, details_failed=failed)

            details, detail_failed = adapter.fetch_details([str(item.get("id")) for item in listed], on_progress)
        records = []
        skipped = 0
        for item in listed:
            detail = details.get(str(item.get("id")))
            record = normalize_charge_point(item, detail)
            if record is None:
                skipped += 1
            else:
                records.append(record)
        clusters = cluster_charge_points(records)
        patch_stats(run_id, phase="persist", listed=len(listed), clusters=len(clusters), skipped=skipped)
        persisted = 0
        cluster_errors = 0
        for cluster in clusters:
            try:
                with session_scope() as session:
                    source = get_source(session, "sharinet")
                    persist_sharinet_cluster(session, source, cluster)
                persisted += 1
            except Exception:
                cluster_errors += 1
                logger.exception("sharinet cluster failed")
        if persisted == 0 and records:
            raise RuntimeError("هیچ ایستگاهی از شارینت ذخیره نشد.")
        with session_scope() as session:
            source = get_source(session, "sharinet")
            missing = withdraw_missing_charge_points(session, source, {record.external_id for record in records})
            hidden = hide_empty_locations(session)
        _finish(
            run_id,
            listed=len(listed),
            locations=persisted,
            charge_points=len(records),
            skipped=skipped,
            details_failed=detail_failed,
            cluster_errors=cluster_errors,
            missing=missing,
            hidden=hidden,
            include_details=include_details,
        )
    finally:
        adapter.close()


def _run_ocm(run_id: uuid.UUID) -> None:
    adapter = OcmAdapter(settings.ocm_api_key)
    try:
        patch_stats(run_id, phase="reference")
        adapter.load_reference()
        patch_stats(run_id, phase="fetch", operators=len(adapter.operators))
        pois = adapter.fetch_iran()
        records, dropped, warnings = adapter.normalize_all(pois)
        truncated = any("maxresults" in warning for warning in warnings)
        persisted = 0
        errors = 0
        patch_stats(run_id, phase="persist", fetched=len(pois), records=len(records))
        for record in records:
            try:
                with session_scope() as session:
                    persist_catalog_record(session, get_source(session, "ocm"), record)
                persisted += 1
            except Exception:
                errors += 1
                logger.exception("ocm record %s failed", record.external_id)
        missing = 0
        if not truncated:
            with session_scope() as session:
                missing = withdraw_missing_locations(
                    session, get_source(session, "ocm"), {record.external_id for record in records}
                )
                hide_empty_locations(session)
        _finish(
            run_id,
            fetched=len(pois),
            persisted=persisted,
            dropped=len(dropped),
            errors=errors,
            missing=missing,
            truncated=truncated,
            warnings=warnings,
        )
    finally:
        adapter.close()


def _run_abrp(run_id: uuid.UUID) -> None:
    adapter = AbrpAdapter(settings.abrp_api_key)
    try:
        patch_stats(run_id, phase="fetch")
        chargers, warnings = adapter.fetch_iran()
        records = []
        linked = 0
        for item in chargers:
            record = normalize_charger(item)
            if record is None:
                continue
            if record.ocm_external_id:
                linked += 1
            records.append(record)
        persisted = 0
        errors = 0
        patch_stats(run_id, phase="persist", fetched=len(chargers), records=len(records), ocm_links=linked)
        for record in records:
            try:
                with session_scope() as session:
                    persist_catalog_record(session, get_source(session, "abrp"), record)
                persisted += 1
            except Exception:
                errors += 1
                logger.exception("abrp record %s failed", record.external_id)
        with session_scope() as session:
            missing = withdraw_missing_locations(
                session, get_source(session, "abrp"), {record.external_id for record in records}
            )
            hide_empty_locations(session)
        _finish(
            run_id,
            fetched=len(chargers),
            persisted=persisted,
            ocm_links=linked,
            errors=errors,
            missing=missing,
            warnings=warnings,
        )
    finally:
        adapter.close()


def latest_runs(session) -> dict[str, SyncRun]:
    sources = session.scalars(select(SourceSystem)).all()
    found: dict[str, SyncRun] = {}
    for source in sources:
        run = session.scalar(
            select(SyncRun).where(SyncRun.source_system_id == source.id).order_by(SyncRun.started_at.desc())
        )
        if run is not None:
            found[source.code] = run
    return found
