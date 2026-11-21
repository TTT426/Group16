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
