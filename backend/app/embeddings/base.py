from typing import Protocol, runtime_checkable


@runtime_checkable
class Embedder(Protocol):
    name: str
    # Identifies the exact model, e.g. "fastembed:BAAI/bge-small-zh-v1.5". Stored with every vector,
    # so vectors from different models are never compared.
    model_id: str

    def embed(self, texts: list[str]) -> list[list[float]]:
        """Embed documents / chunks. Vectors are L2-normalised."""
        ...

    def embed_query(self, text: str) -> list[float]: ...
