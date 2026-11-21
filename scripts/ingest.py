"""Index documents into the database.

Examples:
  python scripts/ingest.py github notion discord          # real tools (tokens in .env)
  python scripts/ingest.py --scenario scripts/seed_workspace/scenario_*.yaml   # offline simulated workspace
  python scripts/ingest.py --init-db --scenario ...       # also create tables first
"""

import argparse
import glob
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))

from app.config import get_settings  # noqa: E402
from app.connectors.factory import SOURCES, build_connector  # noqa: E402
from app.connectors.scenario import ScenarioConnector  # noqa: E402
from app.db.session import get_session_factory, init_db  # noqa: E402
from app.embeddings.factory import get_embedder  # noqa: E402
from app.ingest.pipeline import ingest_documents  # noqa: E402


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("sources", nargs="*", choices=SOURCES, help="real tools to ingest")
    parser.add_argument("--scenario", nargs="+", default=[], help="scenario YAML files (globs allowed)")
    parser.add_argument("--init-db", action="store_true", help="create extensions and tables first")
    args = parser.parse_args()
    if not args.sources and not args.scenario:
        parser.error("give at least one source or --scenario")

    if args.init_db:
        init_db()
    settings, embedder = get_settings(), get_embedder()
    results = {}
    with get_session_factory()() as session:
        if args.scenario:
            paths = sorted({p for pattern in args.scenario for p in glob.glob(pattern)})
            results["scenario"] = ingest_documents(session, ScenarioConnector(paths).fetch(), embedder).as_dict()
        for name in args.sources:
            results[name] = ingest_documents(session, build_connector(name, settings).fetch(), embedder).as_dict()
    print(json.dumps(results, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
