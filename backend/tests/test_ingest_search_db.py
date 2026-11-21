"""Ingest + hybrid search against a real (temporary) SQLite database."""

import os

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select

from app.api.deps import chunk_index_dep, embedder_dep
from app.connectors.base import NormalizedDocument
from app.connectors.scenario import ScenarioConnector
from app.db.models import Chunk, Document
from app.db.session import get_session
from app.embeddings.hashing import HashingEmbedder
from app.ingest.pipeline import ingest_documents, reembed_stale
from app.main import app
from app.retrieval.hybrid import ChunkIndex, HybridRetriever


@pytest.fixture
def embedder():
    return HashingEmbedder()


@pytest.fixture
def ingested(db_session, embedder, scenario_paths):
    connector = ScenarioConnector(scenario_paths)
    stats = ingest_documents(db_session, connector.fetch(), embedder)
    return connector, stats


def test_ingest_scenarios(db_session, ingested):
    _, stats = ingested
    assert stats.documents == db_session.scalar(select(func.count(Document.id)))
    assert stats.chunks == db_session.scalar(select(func.count(Chunk.id)))
    assert set(stats.by_source) == {"github", "notion", "discord"}
    assert db_session.scalar(select(func.count(Chunk.id)).where(Chunk.embedding.is_(None))) == 0
    chunk = db_session.scalars(select(Chunk)).first()
    assert chunk.embedding_model == "hashing:512" and len(chunk.embedding) == 512


def test_reingest_is_idempotent_and_updates(db_session, embedder, ingested):
    connector, stats = ingested
    ingest_documents(db_session, connector.fetch(), embedder)
    assert db_session.scalar(select(func.count(Document.id))) == stats.documents
    assert db_session.scalar(select(func.count(Chunk.id))) == stats.chunks

    doc = next(iter(connector.fetch()))
    ingest_documents(db_session, [doc.model_copy(update={"text": "全新內容 updated"})], embedder)
    row = db_session.scalar(select(Document).where(Document.external_id == doc.external_id))
    assert [c.text for c in row.chunks] == [f"[GitHub] {doc.title}\n全新內容 updated"]


def test_search_finds_all_three_answer_sources_for_payment_task(db_session, embedder, ingested):
    connector, _ = ingested
    retriever = HybridRetriever(db_session, embedder, ChunkIndex())
    hits = retriever.search("PAYMENT_DUPLICATE 付款失敗的原因是什麼？為什麼用固定 idempotency key？", top_k=8)
    urls = {h.url for h in hits}
    expected = {connector.urls[k] for k in
                ("discord.thread.payment-fail", "github.pull.fix-idem-key", "notion.page.payment-spec")}
    assert expected <= urls
    assert {h.source for h in hits} == {"github", "notion", "discord"}
    assert all(h.matched_by for h in hits)


def test_link_expansion_pulls_in_referenced_document(db_session, embedder):
    docs = [
        NormalizedDocument(source="discord", external_id="thread:1", url="https://discord.com/channels/9/1",
                           title="討論", text="原因找到了，修正在 https://github.com/acme/shop/pull/5"),
        NormalizedDocument(source="github", external_id="pr:5", url="https://github.com/acme/shop/pull/5",
                           title="Pull request #5: unrelated words", text="zzz qqq"),
    ]
    ingest_documents(db_session, docs, embedder)
    hits = HybridRetriever(db_session, embedder, ChunkIndex()).search("原因找到了", top_k=1)
    assert hits[0].url == "https://discord.com/channels/9/1"
    linked = [h for h in hits if h.matched_by == ["link"]]
    assert [h.url for h in linked] == ["https://github.com/acme/shop/pull/5"]

    no_links = HybridRetriever(db_session, embedder, ChunkIndex()).search("原因找到了", top_k=1, expand_links=False)
    assert len(no_links) == 1


def test_index_refreshes_after_ingest(db_session, embedder):
    index = ChunkIndex()
    assert index.keyword_search(db_session, "anything", 5) == []
    ingest_documents(db_session, [NormalizedDocument(source="notion", external_id="p1", url="u", title="t",
                                                     text="獨特關鍵字 xyzzy")], embedder)
    assert len(index.keyword_search(db_session, "xyzzy", 5)) == 1
    assert len(index.vector_search(db_session, embedder.embed_query("xyzzy"), embedder.model_id, 5)) == 1


def test_vector_search_ranks_by_similarity(db_session, embedder):
    texts = {"a": "部署 staging 流程", "b": "付款失敗 重試 idempotency", "c": "新人 onboarding"}
    ingest_documents(db_session, [NormalizedDocument(source="notion", external_id=k, url=k, title=k, text=t)
                                  for k, t in texts.items()], embedder)
    ids = ChunkIndex().vector_search(db_session, embedder.embed_query("付款 失敗 重試"), embedder.model_id, 3)
    assert db_session.get(Chunk, ids[0]).document.external_id == "b"


def test_vector_search_without_numpy(db_session, embedder, monkeypatch):
    import app.retrieval.hybrid as hybrid

    monkeypatch.setattr(hybrid, "np", None)  # minimal install: pure-Python fallback
    texts = {"a": "部署 staging 流程", "b": "付款失敗 重試 idempotency"}
    ingest_documents(db_session, [NormalizedDocument(source="notion", external_id=k, url=k, title=k, text=t)
                                  for k, t in texts.items()], embedder)
    ids = hybrid.ChunkIndex().vector_search(db_session, embedder.embed_query("付款 失敗"), embedder.model_id, 2)
    assert db_session.get(Chunk, ids[0]).document.external_id == "b"


def test_model_mismatch_warns_and_reembed_fixes_it(db_session, ingested):
    other = HashingEmbedder(64)  # different model_id than the one used for ingest
    retriever = HybridRetriever(db_session, other, ChunkIndex())
    hits = retriever.search("付款失敗", top_k=5)
    assert hits and all("vector" not in h.matched_by for h in hits)  # keyword search still works
    assert retriever.warnings and "re-run the ingest" in retriever.warnings[0]

    assert reembed_stale(db_session, other) > 0
    assert reembed_stale(db_session, other) == 0
    retriever = HybridRetriever(db_session, other, ChunkIndex())
    assert any("vector" in h.matched_by for h in retriever.search("付款失敗", top_k=5))
    assert retriever.warnings == []


def test_search_endpoint(db_session, embedder, ingested):
    app.dependency_overrides[get_session] = lambda: db_session
    app.dependency_overrides[embedder_dep] = lambda: embedder
    app.dependency_overrides[chunk_index_dep] = ChunkIndex
    try:
        client = TestClient(app)
        response = client.get("/search", params={"q": "確認信重複寄送", "top_k": 5})
        assert response.status_code == 200
        body = response.json()
        assert body["results"] and {"url", "source", "title", "text", "matched_by"} <= set(body["results"][0])
        assert body["embedding_model"] == embedder.model_id and body["warnings"] == []
        assert client.get("/search", params={"q": ""}).status_code == 422
        assert "<!doctype html>" in client.get("/").text.lower()
    finally:
        app.dependency_overrides.clear()


@pytest.mark.skipif(
    not os.environ.get("GROUP16_TEST_EMBEDDER"),
    reason="set GROUP16_TEST_EMBEDDER=fastembed to test the real embedding model",
)
def test_real_embedder_finds_answer_sources(db_session, scenario_paths):
    """Same check as above but with a real embedding model, for both scenarios."""
    from app.config import Settings
    from app.embeddings.factory import build_embedder

    embedder = build_embedder(Settings(_env_file=None, embedding_provider=os.environ["GROUP16_TEST_EMBEDDER"]))
    connector = ScenarioConnector(scenario_paths)
    ingest_documents(db_session, connector.fetch(), embedder)
    retriever = HybridRetriever(db_session, embedder, ChunkIndex())
    for scenario in connector.scenarios:
        hits = retriever.search(scenario["task"], top_k=8)
        expected = {connector.urls[k] for k in scenario["answer_key"]["sources"]}
        assert expected <= {h.url for h in hits}, scenario["id"]
