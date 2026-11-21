"""Deterministic hashing embedder: no model download, lexical similarity only.

For tests and offline development. Use `bge` for real semantic search.
"""

import hashlib
import math

from ..retrieval.tokenize import tokenize


class HashingEmbedder:
    name = "hashing"

    def __init__(self, dim: int = 1024) -> None:
        self.dim = dim

    def _vector(self, text: str) -> list[float]:
        vec = [0.0] * self.dim
        for token in tokenize(text):
            digest = hashlib.blake2b(token.encode("utf-8"), digest_size=8).digest()
            index = int.from_bytes(digest[:4], "little") % self.dim
            vec[index] += 1.0 if digest[4] & 1 else -1.0
        norm = math.sqrt(sum(v * v for v in vec))
        if norm == 0:
            vec[0] = 1.0  # pgvector cannot compute cosine distance of a zero vector
            return vec
        return [v / norm for v in vec]

    def embed(self, texts: list[str]) -> list[list[float]]:
        return [self._vector(t) for t in texts]

    def embed_query(self, text: str) -> list[float]:
        return self._vector(text)
