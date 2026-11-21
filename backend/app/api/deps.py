"""Shared FastAPI dependencies (overridable in tests via app.dependency_overrides)."""

from functools import lru_cache

from ..config import get_settings
from ..embeddings.base import Embedder
from ..embeddings.factory import get_embedder
from ..llm.base import LLMProvider
from ..llm.factory import get_provider
from ..qa.workspace import WorkspaceExport
from ..retrieval.hybrid import ChunkIndex


def embedder_dep() -> Embedder:
    return get_embedder()


@lru_cache
def chunk_index_dep() -> ChunkIndex:
    return ChunkIndex()


@lru_cache
def llm_dep() -> LLMProvider:
    return get_provider(get_settings())


@lru_cache
def workspace_dep() -> WorkspaceExport:
    return WorkspaceExport(get_settings().workspace_dir)
