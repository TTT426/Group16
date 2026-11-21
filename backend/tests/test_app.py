from fastapi.testclient import TestClient

from app.db import models
from app.main import app


def test_health():
    response = TestClient(app).get("/health")
    assert response.status_code == 200
    assert response.json()["status"] == "ok"


def test_schema_tables_defined():
    tables = set(models.Base.metadata.tables)
    assert {"documents", "chunks", "answers", "decisions", "decision_confirmations",
            "eval_sessions", "events"} <= tables



def test_database_path_relative_to_repo(tmp_path):
    from app.config import REPO_ROOT, Settings
    from app.db.session import create_db_engine, delete_db_file, init_db

    assert Settings(_env_file=None, database_path="data/x.db").db_file == REPO_ROOT / "data" / "x.db"
    db = tmp_path / "nested" / "dir" / "app.db"
    engine = create_db_engine(db)  # creates missing parent folders
    init_db(engine)
    engine.dispose()
    assert db.exists()
    delete_db_file(db)
    assert not db.exists()
