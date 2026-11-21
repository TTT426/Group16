from typing import Protocol, runtime_checkable


@runtime_checkable
class Embedder(Protocol):
    name: str
    dim: int

    def embed(self, texts: list[str]) -> list[list[float]]:
        """Embed documents / chunks. Vectors are L2-normalised."""
        ...

    def embed_query(self, text: str) -> list[float]: ...
