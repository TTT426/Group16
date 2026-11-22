"""Index documents into the database.

Examples:
  python scripts/ingest.py github notion discord          # real tools (tokens in .env)
  python scripts/ingest.py --seed-repo github             # GitHub from SEED_GITHUB_REPO (the evaluation workspace)
  python scripts/ingest.py --scenario scripts/seed_workspace/scenario_*.yaml   # offline simulated workspace
  python scripts/ingest.py --init-db --if-empty --scenario ...   # first run only (used by start.bat)
"""

import argparse
import glob
import json
import sys
from pathlib import Path

from sqlalchemy import func, select

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))

from app.config import get_settings  # noqa: E402
from app.connectors.factory import SOURCES, build_connector  # noqa: E402
from app.connectors.scenario import ScenarioConnector  # noqa: E402
from app.db.models import Document  # noqa: E402
from app.db.session import delete_db_file, get_session_factory, init_db  # noqa: E402
from app.embeddings.factory import get_embedder  # noqa: E402
from app.ingest.pipeline import ingest_documents, reembed_stale  # noqa: E402


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("sources", nargs="*", choices=SOURCES, help="real tools to ingest")
    parser.add_argument("--scenario", nargs="+", default=[], help="scenario YAML files (globs allowed)")
    parser.add_argument("--init-db", action="store_true", help="create tables first (safe to repeat)")
    parser.add_argument("--reset", action="store_true", help="delete the SQLite database file first")
    parser.add_argument("--seed-repo", action="store_true",
                        help="read GitHub from SEED_GITHUB_REPO (the seeded evaluation workspace), not GITHUB_REPO")
    parser.add_argument("--if-empty", action="store_true",
                        help="skip if documents already exist (only re-embed chunks made with another model)")
    args = parser.parse_args()
    if not args.sources and not args.scenario:
        parser.error("give at least one source or --scenario")

    settings, embedder = get_settings(), get_embedder()
    if args.seed_repo:
        if not settings.seed_github_repo:
            parser.error("--seed-repo needs SEED_GITHUB_REPO in .env")
        settings = settings.model_copy(update={"github_repo": settings.seed_github_repo})
    if args.reset:
        delete_db_file(settings.db_file)
        print(f"Deleted {settings.db_file}")
    if args.init_db or args.reset:
        init_db()
    results = {}
    with get_session_factory()() as session:
        print(f"Embedding model: {embedder.model_id}", flush=True)
        if args.if_empty and session.scalar(select(func.count(Document.id))):
            updated = reembed_stale(session, embedder)
            note = f"; re-embedded {updated} chunks for the current model" if updated else ""
            print(f"Database already has documents, skipping ingest{note}.")
            return
        if args.scenario:
            paths = sorted({p for pattern in args.scenario for p in glob.glob(pattern)})
            results["scenario"] = ingest_documents(session, ScenarioConnector(paths).fetch(), embedder).as_dict()
        for name in args.sources:
            results[name] = ingest_documents(session, build_connector(name, settings).fetch(), embedder).as_dict()
    print(json.dumps(results, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
