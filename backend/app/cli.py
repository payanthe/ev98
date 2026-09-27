import argparse
import uuid

from app.core.db import session_scope
from app.ingestion.seed import ensure_sources
from app.ingestion.service import execute_sync, start_sync


def main() -> None:
    parser = argparse.ArgumentParser(description="EV98 ingestion")
    sub = parser.add_subparsers(dest="command", required=True)
    sync = sub.add_parser("sync")
    sync.add_argument("source", choices=["sharinet", "ocm", "abrp"])
    sync.add_argument("--no-details", action="store_true")
    reconcile = sub.add_parser("reconcile-locations")
    reconcile.add_argument("--dry-run", action="store_true")
    resolve = sub.add_parser("resolve-duplicate")
    resolve.add_argument("candidate_id")
    resolve.add_argument("decision", choices=["merge", "distinct"])
    sub.add_parser("list-duplicates")
    args = parser.parse_args()

    if args.command == "reconcile-locations":
        from app.ingestion.reconcile import reconcile_locations

        with session_scope() as session:
            stats = reconcile_locations(session, dry_run=args.dry_run)
            if args.dry_run:
                session.rollback()
        print(stats)
        return
    if args.command == "resolve-duplicate":
        from app.ingestion.reconcile import resolve_candidate

        with session_scope() as session:
            candidate = resolve_candidate(session, uuid.UUID(args.candidate_id), args.decision)
            print(candidate.id, candidate.status)
        return
    if args.command == "list-duplicates":
        from sqlalchemy import select

        from app.models.entities import DuplicateCandidate, Location

        with session_scope() as session:
            candidates = session.scalars(
                select(DuplicateCandidate)
                .where(DuplicateCandidate.status == "pending")
                .order_by(DuplicateCandidate.confidence.desc())
            ).all()
            for candidate in candidates:
                left = session.get(Location, candidate.left_location_id)
                right = session.get(Location, candidate.right_location_id)
                print(
                    candidate.id,
                    float(candidate.confidence),
                    f"{candidate.evidence.get('distance_m', '?')}m",
                    repr(left.canonical_name_fa if left else "missing"),
                    "<>",
                    repr(right.canonical_name_fa if right else "missing"),
                )
        return

    with session_scope() as session:
        ensure_sources(session)
    with session_scope() as session:
        run = start_sync(session, args.source, include_details=not args.no_details)
        run_id: uuid.UUID = run.id
    execute_sync(run_id)
    with session_scope() as session:
        from app.models.entities import SyncRun

        finished = session.get(SyncRun, run_id)
        print(finished.status if finished else "missing", finished.stats if finished else "", finished.error or "")


if __name__ == "__main__":
    main()
