from functools import lru_cache

from ..config import Settings, get_settings
from .base import Embedder


def build_embedder(settings: Settings) -> Embedder:
    name = settings.embedding_provider.strip().lower()
    if name == "bge":
        from .bge import SentenceTransformerEmbedder

        return SentenceTransformerEmbedder(settings.embedding_model, settings.embedding_dim)
    if name == "hashing":
        from .hashing import HashingEmbedder

        return HashingEmbedder(settings.embedding_dim)
    raise ValueError(f"Unknown EMBEDDING_PROVIDER {name!r}. Use 'bge' or 'hashing'.")


@lru_cache
def get_embedder() -> Embedder:
    """Process-wide embedder (loading the model is expensive)."""
    return build_embedder(get_settings())
