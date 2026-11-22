"""AI question answering over the indexed project, in three modes.

- rag   : hybrid search picks the relevant passages, one LLM call summarises them.
- full  : every document goes into the prompt ("the whole project as memory"), one LLM call.
          Falls back to rag when the project is larger than QA_FULL_CONTEXT_CHARS.
- agent : the project is exported as markdown files and Claude Code searches them itself with
          its read-only Grep / Glob / Read tools before answering. Only providers that can search a
          folder (`supports_workspace`, i.e. the Claude CLI) can do this; others fall back to rag.

In every mode the model must cite its sources; citations are checked against what it was given.
"""

from dataclasses import asdict, dataclass, field

from sqlalchemy.orm import Session

from ..config import Settings
from ..embeddings.base import Embedder
from ..llm.base import LLMError, LLMProvider
from ..llm.json_utils import extract_json_object
from ..retrieval.hybrid import ChunkIndex, HybridRetriever
from . import prompts
from .citations import CheckedAnswer, Source, check_answer
from .documents import load_documents
from .workspace import WorkspaceExport

MODES = ("rag", "full", "agent")


class QAError(RuntimeError):
    """The model did not produce a usable answer."""


@dataclass
class QAResult:
    question: str
    mode: str
    sections: list[dict]
    sources: list[dict]  # cited sources, in citation order
    unanswerable: bool
    confidence: str
    missing: str
    suggested_contacts: list[str]
    provider: str
    model: str
    latency_ms: int
    llm_calls: int
    sources_given: int  # how many sources / documents the model could use
    warnings: list[str] = field(default_factory=list)
    dropped_citations: list[str] = field(default_factory=list)

    def as_dict(self) -> dict:
        return asdict(self)


class QAService:
    def __init__(
        self,
        session: Session,
        embedder: Embedder,
        index: ChunkIndex,
        provider: LLMProvider,
        settings: Settings,
        workspace: WorkspaceExport,
    ) -> None:
        self.session = session
        self.embedder = embedder
        self.index = index
        self.provider = provider
        self.settings = settings
        self.workspace = workspace

    async def answer(self, question: str, mode: str | None = None) -> QAResult:
        mode = (mode or self.settings.qa_mode).lower()
        if mode not in MODES:
            raise ValueError(f"Unknown mode {mode!r}. Use one of: {', '.join(MODES)}.")
        warnings: list[str] = []
        calls = 0
        latency = 0

        if mode == "agent" and not getattr(self.provider, "supports_workspace", False):
            warnings.append("目前選擇的 AI 模型不能自己搜尋檔案（agent 模式只支援 Claude Code），已改用 rag 模式。")
            mode = "rag"
        if mode == "agent":
            root = self.workspace.sync(self.session)
            raw, calls, latency, provider, model = await self._ask_json(
                prompts.SYSTEM_AGENT, prompts.agent_prompt(question), workspace=root)
            checked = check_answer(raw, {}, resolve=self._resolve_workspace_path)
            given = len(self.workspace.files)
        else:
            if mode == "full":
                sources = self._full_sources()
                if sum(len(s.text) for s in sources) > self.settings.qa_full_context_chars:
                    warnings.append("專案內容超過完整記憶模式的上限（QA_FULL_CONTEXT_CHARS），已改用 rag 模式。")
                    mode = "rag"
            if mode == "rag":
                retriever = HybridRetriever(self.session, self.embedder, self.index)
                hits = retriever.search(question, self.settings.qa_top_k)
                warnings += retriever.warnings
                sources = [Source(f"S{i}", h.document_id, h.source, h.url, h.title, h.author, h.text)
                           for i, h in enumerate(hits, 1)]
            if not sources:
                return self._empty(question, mode, warnings)
            raw, calls, latency, provider, model = await self._ask_json(
                prompts.SYSTEM_SOURCES, prompts.sources_prompt(question, sources))
            checked = check_answer(raw, {s.id: s for s in sources})
            given = len(sources)

        if checked.dropped_citations:
            warnings.append(f"已移除 {len(checked.dropped_citations)} 個不存在的來源引用。")
        return self._result(question, mode, checked, provider, model, latency, calls, given, warnings)

    # -- helpers ---------------------------------------------------------------------

    async def _ask_json(self, system: str, user: str, workspace=None):
        """One retry for an invalid reply or a transient CLI failure (e.g. an unparsable tool call)."""
        calls, latency = 0, 0
        for attempt in range(2):
            try:
                result = await self.provider.generate(
                    system, user + (prompts.RETRY_NOTE if attempt else ""), workspace=workspace,
                    json_schema=prompts.ANSWER_SCHEMA)
            except LLMError as exc:
                calls += 1
                if attempt or "not found" in str(exc):  # a missing CLI will not fix itself
                    raise
                continue
            calls += 1
            latency += result.latency_ms
            try:
                return extract_json_object(result.text), calls, latency, result.provider, result.model
            except ValueError:
                continue
        raise QAError("模型沒有回傳有效的 JSON 格式答案，請再試一次。")

    def _full_sources(self) -> list[Source]:
        return [Source(f"S{i}", d.id, d.source, d.url, d.title, d.author, d.text)
                for i, d in enumerate(load_documents(self.session), 1)]

    def _resolve_workspace_path(self, cited: str) -> Source | None:
        doc_id = self.workspace.document_id(cited)
        if doc_id is None:
            return None
        docs = load_documents(self.session, [doc_id])
        if not docs:
            return None
        d = docs[0]
        return Source(self.workspace.path_of(doc_id) or cited, d.id, d.source, d.url, d.title, d.author, d.text)

    def _empty(self, question: str, mode: str, warnings: list[str]) -> QAResult:
        return QAResult(question, mode, [], [], True, "low", "目前的資料裡找不到相關內容。", [],
                        self.provider.name, "", 0, 0, 0, warnings + ["沒有可用的資料，請先匯入。"])

    @staticmethod
    def _result(question, mode, checked: CheckedAnswer, provider, model, latency, calls, given, warnings):
        return QAResult(
            question=question,
            mode=mode,
            sections=[asdict(s) for s in checked.sections],
            sources=[s.public() for s in checked.cited],
            unanswerable=checked.unanswerable,
            confidence=checked.confidence,
            missing=checked.missing,
            suggested_contacts=checked.suggested_contacts,
            provider=provider,
            model=model,
            latency_ms=latency,
            llm_calls=calls,
            sources_given=given,
            warnings=warnings,
            dropped_citations=checked.dropped_citations,
        )


__all__ = ["MODES", "QAError", "QAResult", "QAService", "LLMError"]
