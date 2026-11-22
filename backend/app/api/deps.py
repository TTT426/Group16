"""Shared FastAPI dependencies (overridable in tests via app.dependency_overrides)."""

from functools import lru_cache

from ..config import get_settings
from ..embeddings.base import Embedder
from ..embeddings.factory import get_embedder
from ..llm.base import LLMProvider
from ..llm.factory import UnavailableProvider, get_provider
from ..qa.workspace import WorkspaceExport
from ..retrieval.hybrid import ChunkIndex


def embedder_dep() -> Embedder:
    return get_embedder()


@lru_cache
def chunk_index_dep() -> ChunkIndex:
    return ChunkIndex()


@lru_cache
def llm_dep() -> LLMProvider:
    settings = get_settings()
    try:
        return get_provider(settings)
    except ValueError:  # e.g. a typo in a hand-edited .env
        return UnavailableProvider(settings.llm_provider, f"不認得 LLM_PROVIDER={settings.llm_provider}。")


@lru_cache
def workspace_dep() -> WorkspaceExport:
    return WorkspaceExport(get_settings().workspace_dir)
