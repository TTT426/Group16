"""Shared FastAPI dependencies (overridable in tests via app.dependency_overrides)."""

from functools import lru_cache

from ..embeddings.base import Embedder
from ..embeddings.factory import get_embedder
from ..retrieval.hybrid import KeywordIndex


def embedder_dep() -> Embedder:
    return get_embedder()


@lru_cache
def keyword_index_dep() -> KeywordIndex:
    return KeywordIndex()
