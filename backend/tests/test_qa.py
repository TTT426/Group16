"""AI question answering: three modes, citation checking, workspace export (LLM replaced by FakeProvider)."""

import json
import re

import pytest

from app.config import Settings
from app.connectors.scenario import ScenarioConnector
from app.embeddings.hashing import HashingEmbedder
from app.ingest.pipeline import ingest_documents
from app.llm.fake import FakeProvider
from app.qa.citations import Source, check_answer, suggest_contacts
from app.qa.documents import load_documents
from app.qa.service import QAError, QAService
from app.qa.workspace import WorkspaceExport
from app.retrieval.hybrid import ChunkIndex


@pytest.fixture
def embedder():
    return HashingEmbedder()


@pytest.fixture
def ingested(db_session, embedder, scenario_paths):
    connector = ScenarioConnector(scenario_paths)
    ingest_documents(db_session, connector.fetch(), embedder)
    return connector


def cite_first_two(system, user):
    """Fake model: cites the first two source ids it sees, plus one invented id."""
    ids = re.findall(r"^\[(S\d+)\]", user, flags=re.M)
    return json.dumps({"sections": [{"text": "原因是重試時 idempotency key 不同。", "sources": ids[:2] + ["S999"]},
                                    {"text": "沒有來源的一句。", "sources": []}],
                       "unanswerable": False, "confidence": "high", "missing": ""}, ensure_ascii=False)


def make_service(db_session, embedder, provider, tmp_path, **settings):
    cfg = Settings(_env_file=None, workspace_dir=tmp_path / "ws", **settings)
    return QAService(db_session, embedder, ChunkIndex(), provider, cfg, WorkspaceExport(cfg.workspace_dir))


async def test_rag_mode_checks_citations(db_session, embedder, ingested, tmp_path):
    provider = FakeProvider(cite_first_two)
    result = await make_service(db_session, embedder, provider, tmp_path).answer("付款失敗的原因", "rag")
    assert result.mode == "rag" and result.llm_calls == 1
    assert result.sections[0]["sources"] == ["S1", "S2"] and result.sections[0]["supported"]
    assert result.sections[1]["supported"] is False
    assert result.dropped_citations == ["S999"] and any("不存在" in w for w in result.warnings)
    assert [s["id"] for s in result.sources] == ["S1", "S2"]
    assert all(s["url"].startswith("https://") and s["snippet"] for s in result.sources)
    assert result.sources_given >= 3
    system, user = provider.calls[0]
    assert "只輸出一個 JSON" in system and "問題：付款失敗的原因" in user


async def test_full_mode_gives_every_document(db_session, embedder, ingested, tmp_path):
    provider = FakeProvider(cite_first_two)
    result = await make_service(db_session, embedder, provider, tmp_path).answer("付款失敗的原因", "full")
    assert result.mode == "full"
    assert result.sources_given == len(load_documents(db_session))
    assert provider.calls[0][1].count("\n[S") + 1 >= result.sources_given  # every document is in the prompt


async def test_full_mode_falls_back_to_rag_when_too_large(db_session, embedder, ingested, tmp_path):
    service = make_service(db_session, embedder, FakeProvider(cite_first_two), tmp_path, qa_full_context_chars=100)
    result = await service.answer("付款失敗的原因", "full")
    assert result.mode == "rag" and any("上限" in w for w in result.warnings)


async def test_agent_mode_searches_exported_workspace(db_session, embedder, ingested, tmp_path):
    def agent(system, user):
        return json.dumps({"sections": [{"text": "修正在 PR。", "sources": ["./github/pr-5.md", "discord/missing.md"]}],
                           "unanswerable": False, "confidence": "medium"})

    provider = FakeProvider(agent)
    result = await make_service(db_session, embedder, provider, tmp_path).answer("付款失敗怎麼修的？", "agent")
    workspace = provider.workspaces[0]
    assert workspace == tmp_path / "ws" and (workspace / "github" / "pr-5.md").exists()
    assert "Grep" in provider.calls[0][0]
    assert result.sections[0]["sources"] == ["github/pr-5.md"]
    assert result.sources[0]["url"] == "https://github.com/example/shoplite/pull/5"
    assert result.dropped_citations == ["discord/missing.md"]


async def test_invalid_json_is_retried_once_then_fails(db_session, embedder, ingested, tmp_path):
    replies = iter(["not json", json.dumps({"sections": [{"text": "ok", "sources": ["S1"]}]})])
    provider = FakeProvider(lambda s, u: next(replies))
    result = await make_service(db_session, embedder, provider, tmp_path).answer("付款", "rag")
    assert result.llm_calls == 2 and "上一次的回覆不是有效的 JSON" in provider.calls[1][1]

    with pytest.raises(QAError):
        broken = FakeProvider(lambda s, u: "still not json")
        await make_service(db_session, embedder, broken, tmp_path).answer("付款", "rag")


async def test_empty_database_answers_without_calling_llm(db_session, embedder, tmp_path):
    provider = FakeProvider(cite_first_two)
    result = await make_service(db_session, embedder, provider, tmp_path).answer("任何問題", "rag")
    assert result.unanswerable and provider.calls == []


async def test_unknown_mode_rejected(db_session, embedder, tmp_path):
    with pytest.raises(ValueError):
        await make_service(db_session, embedder, FakeProvider(), tmp_path).answer("q", "magic")


def test_check_answer_normalises_input():
    sources = {"S1": Source("S1", 1, "github", "u1", "t1", "amy", "x")}
    raw = {"sections": ["純文字段落", {"text": " ", "sources": ["S1"]}, {"text": "a", "sources": ["[S1]"]}],
           "confidence": "VERY"}
    checked = check_answer(raw, sources)
    assert [s.text for s in checked.sections] == ["純文字段落", "a"]
    assert checked.sections[1].sources == ["S1"]
    assert checked.confidence == "low"
    assert check_answer({}, sources).unanswerable


def test_suggest_contacts_ranks_authors():
    s = [Source(f"S{i}", i, "github", "u", "t", a, "") for i, a in enumerate(["lisa", "kevin", "lisa", None])]
    assert suggest_contacts(s) == ["lisa", "kevin"]


def test_workspace_export_and_path_resolution(db_session, embedder, ingested, tmp_path):
    export = WorkspaceExport(tmp_path / "ws")
    root = export.sync(db_session)
    files = export.files
    assert len(files) == len(load_documents(db_session))
    text = (root / "notion").glob("*.md").__next__().read_text(encoding="utf-8")
    assert text.startswith("# ") and "- url: https://www.notion.so/" in text
    some_path, doc_id = next(iter(files.items()))
    assert export.document_id(f"./{some_path}") == doc_id
    assert export.document_id(str(root / some_path)) == doc_id
    assert export.document_id(some_path.split("/", 1)[1]) == doc_id  # without the folder, if unambiguous
    assert export.document_id("nope.md") is None

    marker = root / "stale.txt"
    marker.write_text("x")
    export.sync(db_session)
    assert marker.exists()  # unchanged corpus: not rebuilt
    ingest_documents(db_session, [next(iter(ingested.fetch())).model_copy(update={"text": "changed"})], embedder)
    export.sync(db_session)
    assert not marker.exists()  # corpus changed: rebuilt


async def test_answer_requests_structured_output(db_session, embedder, ingested, tmp_path):
    from app.qa.prompts import ANSWER_SCHEMA

    provider = FakeProvider(cite_first_two)
    await make_service(db_session, embedder, provider, tmp_path).answer("付款失敗的原因", "rag")
    assert provider.schemas == [ANSWER_SCHEMA]


async def test_transient_cli_error_is_retried_once(db_session, embedder, ingested, tmp_path):
    from app.llm.base import LLMError

    class Flaky(FakeProvider):
        def __init__(self, failures):
            super().__init__(cite_first_two)
            self.failures = failures

        async def generate(self, *args, **kwargs):
            if self.failures:
                self.failures -= 1
                raise LLMError("Claude CLI error (exit 1): The model's tool call could not be parsed")
            return await super().generate(*args, **kwargs)

    result = await make_service(db_session, embedder, Flaky(1), tmp_path).answer("付款", "rag")
    assert result.llm_calls == 2 and result.sections
    with pytest.raises(LLMError):
        await make_service(db_session, embedder, Flaky(2), tmp_path).answer("付款", "rag")
