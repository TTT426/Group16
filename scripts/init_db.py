"""Create DB extensions and tables.  Usage:  docker compose up -d db && python scripts/init_db.py"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))

from app.db.session import init_db  # noqa: E402

if __name__ == "__main__":
    init_db()
    print("Database initialised.")
