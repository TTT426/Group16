import importlib.util
import logging
from functools import lru_cache

from ..config import Settings, get_settings
from .base import Embedder

log = logging.getLogger(__name__)


def _installed(module: str) -> bool:
    return importlib.util.find_spec(module) is not None


def build_embedder(settings: Settings) -> Embedder:
    name = settings.embedding_provider.strip().lower()
    if name == "auto":
        if _installed("fastembed"):
            name = "fastembed"
        else:
            log.warning("fastembed is not installed; using keyword-style hashing embeddings. "
                        'For semantic search: pip install -e ".[embeddings]"')
            name = "hashing"

    if name == "fastembed":
        from .fastembed_model import FastEmbedEmbedder

        return FastEmbedEmbedder(settings.embedding_model)
    if name == "hashing":
        from .hashing import HashingEmbedder

        return HashingEmbedder()
    raise ValueError(f"Unknown EMBEDDING_PROVIDER {name!r}. Use auto, fastembed or hashing.")


@lru_cache
def get_embedder() -> Embedder:
    """Process-wide embedder (loading a model is expensive)."""
    return build_embedder(get_settings())
