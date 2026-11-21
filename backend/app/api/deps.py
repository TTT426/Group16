"""Shared FastAPI dependencies (overridable in tests via app.dependency_overrides)."""

from functools import lru_cache

from ..embeddings.base import Embedder
from ..embeddings.factory import get_embedder
from ..retrieval.hybrid import ChunkIndex


def embedder_dep() -> Embedder:
    return get_embedder()


@lru_cache
def chunk_index_dep() -> ChunkIndex:
    return ChunkIndex()
