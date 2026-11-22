"""End-to-end API flows with a temporary SQLite database and the fake LLM:
ask -> source click -> evaluation metrics -> citation labels -> CSV, and decision draft -> confirm -> searchable."""

import json
import re

import pytest
from fastapi.testclient import TestClient

from app.api.deps import chunk_index_dep, embedder_dep, llm_dep, workspace_dep
from app.config import Settings
from app.connectors.scenario import ScenarioConnector
from app.db.models import Base
from app.db.session import add_missing_columns, create_db_engine, get_session
from app.embeddings.hashing import HashingEmbedder
from app.ingest.pipeline import ingest_documents
from app.llm.fake import FakeProvider
from app.main import app
from app.qa.workspace import WorkspaceExport
from app.retrieval.hybrid import ChunkIndex


def fake_llm(system, user):
    if "決策紀錄" in system:
        return json.dumps({"title": "付款重試使用固定 idempotency key", "context": "重試造成 PAYMENT_DUPLICATE",
                           "decision": "每筆訂單固定 key，重試前先查狀態", "rationale": "符合 PayNow 規格"},
                          ensure_ascii=False)
    ids = re.findall(r"^\[(S\d+)\]", user, flags=re.M)
    return json.dumps({"sections": [{"text": "原因是 key 每次都不同。", "sources": ids[:2]}],
                       "unanswerable": False, "confidence": "high"}, ensure_ascii=False)


@pytest.fixture
def client(db_session, scenario_paths, tmp_path):
    embedder = HashingEmbedder()
    ingest_documents(db_session, ScenarioConnector(scenario_paths).fetch(), embedder)
    index = ChunkIndex()
    provider = FakeProvider(fake_llm)
    workspace = WorkspaceExport(tmp_path / "ws")
    app.dependency_overrides.update({
        get_session: lambda: db_session, embedder_dep: lambda: embedder, chunk_index_dep: lambda: index,
        llm_dep: lambda: provider, workspace_dep: lambda: workspace,
    })
    try:
        yield TestClient(app)
    finally:
        app.dependency_overrides.clear()


def test_pages_and_static_files_are_served(client):
    for path in ("/", "/observer", "/decisions"):
        r = client.get(path)
        assert r.status_code == 200 and "<!doctype html>" in r.text.lower()
    assert client.get("/static/common.js").status_code == 200
    assert client.get("/static/app.css").status_code == 200


def test_evaluation_flow(client):
    s = client.post("/api/eval/sessions", json={"pair_id": "P1", "participant": "小明", "round": "tool",
                                                 "mode": "ai", "scenario": "payment-failure"}).json()
    sid = s["id"]
    assert client.post("/api/eval/sessions", json={"pair_id": "P1", "participant": "x", "round": "tool",
                                                    "scenario": "s"}).status_code == 400  # tool round needs a mode
    assert client.post(f"/api/eval/sessions/{sid}/end").status_code == 400  # not started
    client.post(f"/api/eval/sessions/{sid}/start")

    answer = client.post("/ask", json={"question": "付款失敗的原因是什麼？", "session_id": sid}).json()
    assert answer["answer_id"] and answer["sources"] and answer["mode"] == "rag"
    client.get("/search", params={"q": "付款", "session_id": sid})

    source = answer["sources"][0]
    r = client.get("/go", params={"url": source["url"], "session_id": sid, "answer_id": answer["answer_id"],
                                  "source_id": source["id"]}, follow_redirects=False)
    assert r.status_code == 302 and r.headers["location"] == source["url"]
    assert client.get("/go", params={"url": "https://evil.example.com"}, follow_redirects=False).status_code == 404

    client.patch(f"/api/eval/sessions/{sid}", json={"senior_delta": 1})
    client.patch(f"/api/eval/sessions/{sid}", json={"senior_delta": 1})
    client.patch(f"/api/eval/sessions/{sid}", json={"senior_delta": -1, "score": 90, "notes": "很快找到"})
    client.post(f"/api/eval/sessions/{sid}/end")

    labels = [{"section_index": 0, "source_id": source["id"], "supported": True}]
    if len(answer["sections"][0]["sources"]) > 1:
        labels.append({"section_index": 0, "source_id": answer["sections"][0]["sources"][1], "supported": False})
    client.post(f"/api/eval/answers/{answer['answer_id']}/labels", json={"labels": labels, "labeled_by": "觀察者"})
    client.post(f"/api/eval/answers/{answer['answer_id']}/labels", json={"labels": labels[:1]})  # update, no duplicate

    m = client.get(f"/api/eval/sessions/{sid}").json()
    assert m["ai_questions"] == 1 and m["searches"] == 1 and m["source_clicks"] == 1 and m["opened_sources"]
    assert m["senior_questions"] == 1 and m["score"] == 90 and m["notes"] == "很快找到"
    assert m["duration_s"] is not None and m["citations_labelled"] == len(labels)
    assert m["citations_supported"] == 1

    answers = client.get("/api/eval/answers", params={"session_id": sid}).json()
    assert answers[0]["labels"] and answers[0]["question"] == "付款失敗的原因是什麼？"

    csv_text = client.get("/api/eval/export.csv").text
    assert csv_text.startswith("﻿id,pair_id") and "小明" in csv_text
    assert client.get("/api/eval/summary").json()["citations_labelled"] == len(labels)


def test_ask_errors(client):
    from app.llm.base import LLMError

    class Broken(FakeProvider):
        async def generate(self, *a, **k):
            raise LLMError("Claude CLI not found")

    app.dependency_overrides[llm_dep] = lambda: Broken()
    r = client.post("/ask", json={"question": "付款"})
    assert r.status_code == 503 and "Claude CLI" in r.json()["detail"]
    assert client.post("/ask", json={"question": ""}).status_code == 422
    assert client.post("/ask", json={"question": "x", "mode": "magic"}).status_code == 422


def test_decision_flow_feeds_back_into_search(client):
    answer = client.post("/ask", json={"question": "付款失敗的原因是什麼？"}).json()
    d = client.post("/api/decisions/draft", json={"answer_id": answer["answer_id"], "created_by": "小明",
                                                  "participants": ["小明", "Lisa", "小明"]}).json()
    assert d["status"] == "pending" and d["title"] == "付款重試使用固定 idempotency key"
    assert d["required_participants"] == ["小明", "Lisa"] and d["source_urls"]

    client.post(f"/api/decisions/{d['id']}/confirm", json={"participant": "小明"})
    edited = client.patch(f"/api/decisions/{d['id']}", json={"rationale": "符合 PayNow 規格，且保留弱網重試"}).json()
    assert edited["confirmed_by"] == []  # editing invalidates earlier confirmations
    assert client.post(f"/api/decisions/{d['id']}/confirm", json={"participant": "陌生人"}).status_code == 400

    client.post(f"/api/decisions/{d['id']}/confirm", json={"participant": "小明"})
    done = client.post(f"/api/decisions/{d['id']}/confirm", json={"participant": "Lisa"}).json()
    assert done["status"] == "confirmed" and done["confirmed_at"]
    assert client.patch(f"/api/decisions/{d['id']}", json={"title": "x"}).status_code == 400  # locked

    results = client.get("/search", params={"q": "保留弱網重試 決策"}).json()["results"]
    assert any(r["source"] == "decision" and r["url"] == f"/decisions#d{d['id']}" for r in results)
    assert client.get("/go", params={"url": f"/decisions#d{d['id']}"}, follow_redirects=False).status_code == 302
    md = client.get("/api/decisions/export.md").text
    assert "付款重試使用固定 idempotency key（已確認）" in md and "**Participants:** 小明, Lisa" in md


def test_decision_draft_falls_back_when_llm_fails(client):
    answer = client.post("/ask", json={"question": "付款失敗的原因是什麼？"}).json()
    app.dependency_overrides[llm_dep] = lambda: FakeProvider(lambda s, u: "not json")
    d = client.post("/api/decisions/draft", json={"answer_id": answer["answer_id"], "created_by": "小明",
                                                  "participants": ["小明"]}).json()
    assert d["title"] == "付款失敗的原因是什麼？" and "key" in d["decision"]
    assert client.post("/api/decisions/draft", json={"answer_id": 9999, "created_by": "a",
                                                     "participants": ["a"]}).status_code == 400


def test_config_lists_modes_and_scenarios(client):
    cfg = client.get("/api/config").json()
    assert cfg["qa_modes"] == ["rag", "full", "agent"] and {s["id"] for s in cfg["scenarios"]} == {
        "payment-failure", "duplicate-email"}


def test_config_uses_injected_session_without_opening_local_database(client, db_session, tmp_path, monkeypatch):
    from sqlalchemy import func, select

    from app.db import session as db
    from app.db.models import Document

    local_db = tmp_path / "uninitialized-local.db"
    monkeypatch.setattr(db, "get_settings", lambda: Settings(_env_file=None, database_path=local_db))
    db.get_session_factory.cache_clear()
    try:
        response = client.get("/api/config")
        assert response.status_code == 200
        expected = dict(db_session.execute(
            select(Document.source, func.count(Document.id)).group_by(Document.source)
        ).all())
        assert expected and response.json()["documents"] == expected
        assert not local_db.exists()  # Config must use the same injected DB as the other endpoints.
    finally:
        db.get_session_factory.cache_clear()


def test_add_missing_columns_upgrades_old_database(tmp_path):
    from sqlalchemy import text

    engine = create_db_engine(tmp_path / "old.db")
    with engine.begin() as conn:  # an eval_sessions table from an older release, without notes / created_at
        conn.execute(text("CREATE TABLE eval_sessions (id INTEGER PRIMARY KEY, pair_id VARCHAR(32), participant "
                          "VARCHAR(255), role VARCHAR(16), round VARCHAR(16), mode VARCHAR(16), scenario VARCHAR(64), "
                          "started_at DATETIME, ended_at DATETIME, senior_questions INTEGER, score FLOAT)"))
    Base.metadata.create_all(engine)
    added = add_missing_columns(engine, Base.metadata)
    assert "eval_sessions.notes" in added and "eval_sessions.created_at" in added
    assert add_missing_columns(engine, Base.metadata) == []
    engine.dispose()


def test_settings_defaults():
    s = Settings(_env_file=None)
    assert s.llm_provider == "claude_cli" and s.qa_mode in ("rag", "full", "agent")
