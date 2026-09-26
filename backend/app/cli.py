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
    args = parser.parse_args()

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
